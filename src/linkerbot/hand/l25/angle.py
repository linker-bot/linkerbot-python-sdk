"""Angle control and sensing for L25 robotic hand.

This module provides the AngleManager class for controlling joint angles
and reading angle sensor data via CAN bus communication. L25 has 16
degrees of freedom split across five CAN frames (0x41-0x45), one per finger.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass

import can

from linkerbot.comm import CANMessageDispatcher
from linkerbot.exceptions import ValidationError
from linkerbot.relay import DataRelay

_JOINT_COUNT = 16


@dataclass
class L25Angle:
    """Joint angles for L25 hand (0-100 range).

    Attributes:
        thumb_abd: Thumb abduction joint angle (0-100)
        thumb_yaw: Thumb yaw joint angle (0-100)
        thumb_root1: Thumb root1 joint angle (0-100)
        thumb_tip: Thumb tip joint angle (0-100)
        index_abd: Index finger abduction joint angle (0-100)
        index_root1: Index finger root1 joint angle (0-100)
        index_tip: Index finger tip joint angle (0-100)
        middle_abd: Middle finger abduction joint angle (0-100)
        middle_root1: Middle finger root1 joint angle (0-100)
        middle_tip: Middle finger tip joint angle (0-100)
        ring_abd: Ring finger abduction joint angle (0-100)
        ring_root1: Ring finger root1 joint angle (0-100)
        ring_tip: Ring finger tip joint angle (0-100)
        pinky_abd: Pinky finger abduction joint angle (0-100)
        pinky_root1: Pinky finger root1 joint angle (0-100)
        pinky_tip: Pinky finger tip joint angle (0-100)
    """

    thumb_abd: float
    thumb_yaw: float
    thumb_root1: float
    thumb_tip: float
    index_abd: float
    index_root1: float
    index_tip: float
    middle_abd: float
    middle_root1: float
    middle_tip: float
    ring_abd: float
    ring_root1: float
    ring_tip: float
    pinky_abd: float
    pinky_root1: float
    pinky_tip: float

    def to_list(self) -> list[float]:
        """Convert to list of floats in joint order.

        Returns:
            List of 16 joint angles in order: thumb_abd, thumb_yaw,
            thumb_root1, thumb_tip, index_abd, index_root1, index_tip,

            middle_abd, middle_root1, middle_tip, ring_abd, ring_root1,
            ring_tip, pinky_abd, pinky_root1, pinky_tip
        """
        return [
            self.thumb_abd,
            self.thumb_yaw,
            self.thumb_root1,
            self.thumb_tip,
            self.index_abd,
            self.index_root1,
            self.index_tip,
            self.middle_abd,
            self.middle_root1,
            self.middle_tip,
            self.ring_abd,
            self.ring_root1,
            self.ring_tip,
            self.pinky_abd,
            self.pinky_root1,
            self.pinky_tip,
        ]

    @classmethod
    def from_list(cls, values: list[float]) -> "L25Angle":
        """Construct from list of floats (0-100 range).

        Args:
            values: List of 16 float values in 0-100 range

        Returns:
            L25Angle instance

        Raises:
            ValueError: If list doesn't have exactly 16 elements
        """
        if len(values) != _JOINT_COUNT:
            raise ValueError(f"Expected {_JOINT_COUNT} values, got {len(values)}")
        for value in values:
            if not isinstance(value, (float, int)):
                raise ValueError(f"Angle value {value} must be float/int")
            if not 0 <= value <= 100:
                raise ValueError(f"Angle value {value} out of range [0, 100]")
        return cls(
            thumb_abd=values[0],
            thumb_yaw=values[1],
            thumb_root1=values[2],
            thumb_tip=values[3],
            index_abd=values[4],
            index_root1=values[5],
            index_tip=values[6],
            middle_abd=values[7],
            middle_root1=values[8],
            middle_tip=values[9],
            ring_abd=values[10],
            ring_root1=values[11],
            ring_tip=values[12],
            pinky_abd=values[13],
            pinky_root1=values[14],
            pinky_tip=values[15],
        )

    def __getitem__(self, index: int) -> float:
        """Support indexing: angles[0] returns thumb_abd (abduction).

        Args:
            index: Joint index (0-15)

        Returns:
            Joint angle value

        Raises:
            IndexError: If index is out of range
        """
        return self.to_list()[index]

    def __len__(self) -> int:
        """Return number of joints (always 16 for L25)."""
        return _JOINT_COUNT


@dataclass(frozen=True)
class AngleData:
    """Immutable angle data container.

    Attributes:
        angles: L25Angle instance containing joint angles (0-100 range).
        timestamp: Unix timestamp when the data was received.
    """

    angles: L25Angle
    timestamp: float


class AngleManager:
    """Manager for joint angle control and sensing.

    L25 splits 16 joints across five CAN frames, one per finger:
    - 0x41: thumb (abd, yaw, root1, reserve, reserve, tip)
    - 0x42: index (abd, reserve, root1, reserve, reserve, tip)
    - 0x43: middle (abd, reserve, root1, reserve, reserve, tip)
    - 0x44: ring (abd, reserve, root1, reserve, reserve, tip)
    - 0x45: pinky (abd, reserve, root1, reserve, reserve, tip)

    Each frame is 7 bytes: [cmd, abd, yaw/reserve, root1, reserve, reserve, tip].
    For non-thumb fingers, the second position is reserved (None in FRAME_MAP).

    This class provides three access modes for angle operations:
    1. Angle control: set_angles() - send 16 target angles across five CAN frames
    2. Blocking mode: get_blocking() - request and wait for all 16 current angles
    3. Cache reading: get_snapshot() - non-blocking read of cached angles
    """

    _FRAME_MAP: dict[int, list[str | None]] = {
        0x41: ["thumb_abd", "thumb_yaw", "thumb_root1", None, None, "thumb_tip"],
        0x42: ["index_abd", None, "index_root1", None, None, "index_tip"],
        0x43: ["middle_abd", None, "middle_root1", None, None, "middle_tip"],
        0x44: ["ring_abd", None, "ring_root1", None, None, "ring_tip"],
        0x45: ["pinky_abd", None, "pinky_root1", None, None, "pinky_tip"],
    }

    def __init__(self, arbitration_id: int, dispatcher: CANMessageDispatcher) -> None:
        """Initialize the angle manager.

        Args:
            arbitration_id: CAN arbitration ID for angle control/sensing.
            dispatcher: CAN message dispatcher to use for communication.
        """
        self._arbitration_id = arbitration_id
        self._dispatcher = dispatcher
        self._dispatcher.subscribe(self._on_message)
        self._relay = DataRelay[AngleData]()
        self._pending: dict[int, list[float]] = {}
        self._in_flight = False
        self._in_flight_since: float = 0

    def set_angles(self, angles: L25Angle | list[float]) -> None:
        """Send target angles to the robotic hand.

        This method sends 16 target angles across five CAN frames. The hand
        will respond with the current angles, which are automatically cached
        and can be retrieved via get_snapshot().

        Args:
            angles: L25Angle instance or list of 16 target angles (range 0-100 each).

        Raises:
            ValidationError: If angles count is not 16 or values are out of range.

        Example:
            >>> manager.set_angles([50.0] * 16)
        """
        if not isinstance(angles, L25Angle):
            angles = L25Angle.from_list(angles)

        for cmd, fields in self._FRAME_MAP.items():
            data = [cmd] + [
                round(getattr(angles, f) * 255 / 100) if f is not None else 0x00
                for f in fields
            ]
            msg = can.Message(
                arbitration_id=self._arbitration_id,
                data=data,
                is_extended_id=False,
            )
            time.sleep(0.0005)
            self._dispatcher.send(msg)

    def get_blocking(self, timeout_ms: float = 100) -> AngleData:
        """Request and wait for current joint angles (blocking).

        This method sends sensing requests for all five frames and blocks until
        all 16 current angles are received or the timeout expires.

        Args:
            timeout_ms: Maximum time to wait in milliseconds (default: 100).

        Returns:
            AngleData instance containing angles and timestamp.

        Raises:
            TimeoutError: If no response is received within timeout.
            ValidationError: If timeout_ms is not positive.

        Example:
            >>> data = manager.get_blocking(timeout_ms=500)
            >>> print(f"Current angles: {data.angles}")
        """
        if timeout_ms <= 0:
            raise ValidationError("timeout_ms must be positive")
        self._pending.clear()
        self._in_flight = False
        self._send_sense_request()
        return self._relay.wait(timeout_ms / 1000.0)

    def get_snapshot(self) -> AngleData | None:
        """Get the most recent cached angle data (non-blocking).

        Returns:
            AngleData instance or None if no data received yet.

        Example:
            >>> data = manager.get_snapshot()
            >>> if data:
            ...     print(f"Fresh angles: {data.angles}")
        """
        return self._relay.snapshot()

    def _set_event_sink(self, sink: Callable[[AngleData], None]) -> None:
        self._relay.set_sink(sink)

    _IN_FLIGHT_TIMEOUT_S = 0.2

    def _send_sense_request(self) -> None:
        if (
            self._in_flight
            and (time.monotonic() - self._in_flight_since) < self._IN_FLIGHT_TIMEOUT_S
        ):
            return
        self._in_flight = True
        self._in_flight_since = time.monotonic()
        self._pending.clear()
        for cmd in self._FRAME_MAP:
            msg = can.Message(
                arbitration_id=self._arbitration_id,
                data=[cmd],
                is_extended_id=False,
            )
            time.sleep(0.0005)
            self._dispatcher.send(msg)

    def _on_message(self, msg: can.Message) -> None:
        if msg.arbitration_id != self._arbitration_id:
            return

        if len(msg.data) < 2:
            return

        cmd = msg.data[0]
        if cmd not in self._FRAME_MAP:
            return

        expected_fields = self._FRAME_MAP[cmd]
        raw_angles = list(msg.data[1:])

        if len(raw_angles) != len(expected_fields):
            return

        decoded = [v * 100 / 255 for v in raw_angles]
        self._pending[cmd] = decoded

        # Check if all frames have been received
        if set(self._pending.keys()) != set(self._FRAME_MAP.keys()):
            return

        # All frames received -- merge into L25Angle
        kwargs: dict[str, float] = {}
        for frame_cmd, fields in self._FRAME_MAP.items():
            for field, value in zip(fields, self._pending[frame_cmd]):
                if field is not None:
                    kwargs[field] = value

        angles = L25Angle(**kwargs)
        angle_data = AngleData(angles=angles, timestamp=time.time())
        self._in_flight = False
        self._pending.clear()
        self._relay.push(angle_data)
