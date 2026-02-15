"""Speed control and sensing for L25 robotic hand.

This module provides the SpeedManager class for controlling joint speeds
and reading speed sensor data via CAN bus communication. L25 has 16
degrees of freedom split across five CAN frames (0x49-0x4D), one per finger.
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
class L25Speed:
    """Joint speeds for L25 hand (0-100 range).

    Attributes:
        thumb_abd: Thumb abduction joint speed (0-100)
        thumb_yaw: Thumb yaw joint speed (0-100)
        thumb_root1: Thumb root1 joint speed (0-100)
        thumb_tip: Thumb tip joint speed (0-100)
        index_abd: Index finger abduction joint speed (0-100)
        index_root1: Index finger root1 joint speed (0-100)
        index_tip: Index finger tip joint speed (0-100)
        middle_abd: Middle finger abduction joint speed (0-100)
        middle_root1: Middle finger root1 joint speed (0-100)
        middle_tip: Middle finger tip joint speed (0-100)
        ring_abd: Ring finger abduction joint speed (0-100)
        ring_root1: Ring finger root1 joint speed (0-100)
        ring_tip: Ring finger tip joint speed (0-100)
        pinky_abd: Pinky finger abduction joint speed (0-100)
        pinky_root1: Pinky finger root1 joint speed (0-100)
        pinky_tip: Pinky finger tip joint speed (0-100)
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
            List of 16 joint speeds in order: thumb_abd, thumb_yaw,
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
    def from_list(cls, values: list[float]) -> "L25Speed":
        """Construct from list of floats (0-100 range).

        Args:
            values: List of 16 float values in 0-100 range

        Returns:
            L25Speed instance

        Raises:
            ValueError: If list doesn't have exactly 16 elements
        """
        if len(values) != _JOINT_COUNT:
            raise ValueError(f"Expected {_JOINT_COUNT} values, got {len(values)}")
        for value in values:
            if not isinstance(value, (float, int)):
                raise ValueError(f"Speed value {value} must be float/int")
            if not 0 <= value <= 100:
                raise ValueError(f"Speed value {value} out of range [0, 100]")
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
        """Support indexing: speeds[0] returns thumb_abd (abduction).

        Args:
            index: Joint index (0-15)

        Returns:
            Joint speed value

        Raises:
            IndexError: If index is out of range
        """
        return self.to_list()[index]

    def __len__(self) -> int:
        """Return number of joints (always 16 for L25)."""
        return _JOINT_COUNT


@dataclass(frozen=True)
class SpeedData:
    """Immutable speed data container.

    Attributes:
        speeds: L25Speed instance containing joint speeds (0-100 range).
        timestamp: Unix timestamp when the data was received.
    """

    speeds: L25Speed
    timestamp: float


class SpeedManager:
    """Manager for joint speed control and sensing.

    L25 splits 16 joints across five CAN frames, one per finger:
    - 0x49: thumb (abd, yaw, root1, reserve, reserve, tip)
    - 0x4A: index (abd, reserve, root1, reserve, reserve, tip)
    - 0x4B: middle (abd, reserve, root1, reserve, reserve, tip)
    - 0x4C: ring (abd, reserve, root1, reserve, reserve, tip)
    - 0x4D: pinky (abd, reserve, root1, reserve, reserve, tip)

    Each frame is 7 bytes: [cmd, abd, yaw/reserve, root1, reserve, reserve, tip].
    For non-thumb fingers, the second position is reserved (None in FRAME_MAP).

    This class provides three access modes for speed operations:
    1. Speed control: set_speeds() - send 16 target speeds across five CAN frames
    2. Blocking mode: get_blocking() - request and wait for all 16 current speeds
    3. Cache reading: get_snapshot() - non-blocking read of cached speeds
    """

    _FRAME_MAP: dict[int, list[str | None]] = {
        0x49: ["thumb_abd", "thumb_yaw", "thumb_root1", None, None, "thumb_tip"],
        0x4A: ["index_abd", None, "index_root1", None, None, "index_tip"],
        0x4B: ["middle_abd", None, "middle_root1", None, None, "middle_tip"],
        0x4C: ["ring_abd", None, "ring_root1", None, None, "ring_tip"],
        0x4D: ["pinky_abd", None, "pinky_root1", None, None, "pinky_tip"],
    }

    def __init__(self, arbitration_id: int, dispatcher: CANMessageDispatcher) -> None:
        """Initialize the speed manager.

        Args:
            arbitration_id: CAN arbitration ID for speed control/sensing.
            dispatcher: CAN message dispatcher to use for communication.
        """
        self._arbitration_id = arbitration_id
        self._dispatcher = dispatcher
        self._dispatcher.subscribe(self._on_message)
        self._relay = DataRelay[SpeedData]()
        self._pending: dict[int, list[float]] = {}
        self._in_flight = False
        self._in_flight_since: float = 0

    def set_speeds(self, speeds: L25Speed | list[float]) -> None:
        """Send target speeds to the robotic hand.

        This method sends 16 target speeds across five CAN frames. The hand
        will respond with the current speeds, which are automatically cached
        and can be retrieved via get_snapshot().

        Args:
            speeds: L25Speed instance or list of 16 target speeds (range 0-100 each).

        Raises:
            ValidationError: If speeds count is not 16 or values are out of range.

        Example:
            >>> manager.set_speeds([50.0] * 16)
        """
        if not isinstance(speeds, L25Speed):
            speeds = L25Speed.from_list(speeds)

        for cmd, fields in self._FRAME_MAP.items():
            data = [cmd] + [
                round(getattr(speeds, f) * 255 / 100) if f is not None else 0x00
                for f in fields
            ]
            msg = can.Message(
                arbitration_id=self._arbitration_id,
                data=data,
                is_extended_id=False,
            )
            self._dispatcher.send(msg)

    def get_blocking(self, timeout_ms: float = 100) -> SpeedData:
        """Request and wait for current joint speeds (blocking).

        This method sends sensing requests for all five frames and blocks until
        all 16 current speeds are received or the timeout expires.

        Args:
            timeout_ms: Maximum time to wait in milliseconds (default: 100).

        Returns:
            SpeedData instance containing speeds and timestamp.

        Raises:
            TimeoutError: If no response is received within timeout.
            ValidationError: If timeout_ms is not positive.

        Example:
            >>> data = manager.get_blocking(timeout_ms=500)
            >>> print(f"Current speeds: {data.speeds}")
        """
        if timeout_ms <= 0:
            raise ValidationError("timeout_ms must be positive")
        self._pending.clear()
        self._in_flight = False
        self._send_sense_request()
        return self._relay.wait(timeout_ms / 1000.0)

    def get_snapshot(self) -> SpeedData | None:
        """Get the most recent cached speed data (non-blocking).

        Returns:
            SpeedData instance or None if no data received yet.

        Example:
            >>> data = manager.get_snapshot()
            >>> if data:
            ...     print(f"Fresh speeds: {data.speeds}")
        """
        return self._relay.snapshot()

    def _set_event_sink(self, sink: Callable[[SpeedData], None]) -> None:
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
        raw_speeds = list(msg.data[1:])

        if len(raw_speeds) != len(expected_fields):
            return

        decoded = [v * 100 / 255 for v in raw_speeds]
        self._pending[cmd] = decoded

        # Check if all frames have been received
        if set(self._pending.keys()) != set(self._FRAME_MAP.keys()):
            return

        # All frames received -- merge into L25Speed
        kwargs: dict[str, float] = {}
        for frame_cmd, fields in self._FRAME_MAP.items():
            for field, value in zip(fields, self._pending[frame_cmd]):
                if field is not None:
                    kwargs[field] = value

        speeds = L25Speed(**kwargs)
        speed_data = SpeedData(speeds=speeds, timestamp=time.time())
        self._in_flight = False
        self._pending.clear()
        self._relay.push(speed_data)
