"""Torque control and sensing for L20lite robotic hand.

This module provides the TorqueManager class for controlling joint torques
and reading torque sensor data via CAN bus communication.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass

import can

from linkerbot.comm import CANMessageDispatcher
from linkerbot.exceptions import ValidationError
from linkerbot.relay import DataRelay

_JOINT_COUNT = 10


@dataclass
class L20liteTorque:
    """Joint torques for L20lite hand (0-100 range).

    Attributes:
        thumb_flex: Thumb flexion joint torque (0-100)
        thumb_abd: Thumb abduction joint torque (0-100)
        index_flex: Index finger flexion joint torque (0-100)
        middle_flex: Middle finger flexion joint torque (0-100)
        ring_flex: Ring finger flexion joint torque (0-100)
        pinky_flex: Pinky finger flexion joint torque (0-100)
        index_abd: Index finger abduction joint torque (0-100)
        ring_abd: Ring finger abduction joint torque (0-100)
        pinky_abd: Pinky finger abduction joint torque (0-100)
        thumb_yaw: Thumb yaw joint torque (0-100)
    """

    thumb_flex: float
    thumb_abd: float
    index_flex: float
    middle_flex: float
    ring_flex: float
    pinky_flex: float
    index_abd: float
    ring_abd: float
    pinky_abd: float
    thumb_yaw: float

    def to_list(self) -> list[float]:
        """Convert to list of floats in joint order.

        Returns:
            List of 10 joint torques in order: thumb_flex, thumb_abd,
            index_flex, middle_flex, ring_flex, pinky_flex,
            index_abd, ring_abd, pinky_abd, thumb_yaw
        """
        return [
            self.thumb_flex,
            self.thumb_abd,
            self.index_flex,
            self.middle_flex,
            self.ring_flex,
            self.pinky_flex,
            self.index_abd,
            self.ring_abd,
            self.pinky_abd,
            self.thumb_yaw,
        ]

    @classmethod
    def from_list(cls, values: list[float]) -> "L20liteTorque":
        """Construct from list of floats (0-100 range).

        Args:
            values: List of 10 float values in 0-100 range

        Returns:
            L20liteTorque instance

        Raises:
            ValueError: If list doesn't have exactly 10 elements
        """
        if len(values) != _JOINT_COUNT:
            raise ValueError(f"Expected {_JOINT_COUNT} values, got {len(values)}")
        for value in values:
            if not isinstance(value, (float, int)):
                raise ValueError(f"Torque value {value} must be float/int")
            if not 0 <= value <= 100:
                raise ValueError(f"Torque value {value} out of range [0, 100]")
        return cls(
            thumb_flex=values[0],
            thumb_abd=values[1],
            index_flex=values[2],
            middle_flex=values[3],
            ring_flex=values[4],
            pinky_flex=values[5],
            index_abd=values[6],
            ring_abd=values[7],
            pinky_abd=values[8],
            thumb_yaw=values[9],
        )

    def __getitem__(self, index: int) -> float:
        """Support indexing: torques[0] returns thumb_flex.

        Args:
            index: Joint index (0-9)

        Returns:
            Joint torque value

        Raises:
            IndexError: If index is out of range
        """
        return self.to_list()[index]

    def __len__(self) -> int:
        """Return number of joints (always 10 for L20lite)."""
        return _JOINT_COUNT


@dataclass(frozen=True)
class TorqueData:
    """Immutable torque data container.

    Attributes:
        torques: L20liteTorque instance containing joint torques (0-100 range).
        timestamp: Unix timestamp when the data was received.
    """

    torques: L20liteTorque
    timestamp: float


class TorqueManager:
    """Manager for joint torque control and sensing.

    This class provides three access modes for torque operations:
    1. Torque control: set_torques() - send 10 target torques to the hand
    2. Blocking mode: get_blocking() - request and wait for all 10 current torques
    3. Cache reading: get_snapshot() - non-blocking read of cached torques
    """

    _FRAME_MAP: dict[int, list[str]] = {
        0x02: [
            "thumb_flex",
            "thumb_abd",
            "index_flex",
            "middle_flex",
            "ring_flex",
        ],
        0x03: ["pinky_flex", "index_abd", "ring_abd", "pinky_abd", "thumb_yaw"],
    }

    def __init__(self, arbitration_id: int, dispatcher: CANMessageDispatcher) -> None:
        """Initialize the torque manager.

        Args:
            arbitration_id: CAN arbitration ID for torque control/sensing.
            dispatcher: CAN message dispatcher to use for communication.
        """
        self._arbitration_id = arbitration_id
        self._dispatcher = dispatcher
        self._dispatcher.subscribe(self._on_message)
        self._relay = DataRelay[TorqueData]()
        self._pending: dict[int, list[float]] = {}
        self._in_flight = False
        self._in_flight_since: float = 0

    def set_torques(self, torques: L20liteTorque | list[float]) -> None:
        """Send target torques to the robotic hand.

        This method sends 10 target torques to the hand. The hand
        will respond with the current torques, which are automatically cached
        and can be retrieved via get_snapshot().

        Args:
            torques: L20liteTorque instance or list of 10 target torques (range 0-100 each).

        Raises:
            ValidationError: If torques count is not 10 or values are out of range.

        Example:
            >>> manager.set_torques([50.0, 30.0, 60.0, 60.0, 60.0, 60.0, 20.0, 20.0, 20.0, 20.0])
        """
        if not isinstance(torques, L20liteTorque):
            torques = L20liteTorque.from_list(torques)

        for cmd, fields in self._FRAME_MAP.items():
            raw_values = [round(getattr(torques, f) * 255 / 100) for f in fields]
            data = [cmd, *raw_values]
            msg = can.Message(
                arbitration_id=self._arbitration_id,
                data=data,
                is_extended_id=False,
            )
            self._dispatcher.send(msg)

    def get_blocking(self, timeout_ms: float = 100) -> TorqueData:
        """Request and wait for current joint torques (blocking).

        This method sends a sensing request and blocks until
        all 10 current torques are received or the timeout expires.

        Args:
            timeout_ms: Maximum time to wait in milliseconds (default: 100).

        Returns:
            TorqueData instance containing torques and timestamp.

        Raises:
            TimeoutError: If no response is received within timeout.
            ValidationError: If timeout_ms is not positive.

        Example:
            >>> data = manager.get_blocking(timeout_ms=500)
            >>> print(f"Current torques: {data.torques}")
        """
        if timeout_ms <= 0:
            raise ValidationError("timeout_ms must be positive")
        self._pending.clear()
        self._in_flight = False
        self._send_sense_request()
        return self._relay.wait(timeout_ms / 1000.0)

    def get_snapshot(self) -> TorqueData | None:
        """Get the most recent cached torque data (non-blocking).

        Returns:
            TorqueData instance or None if no data received yet.

        Example:
            >>> data = manager.get_snapshot()
            >>> if data:
            ...     print(f"Fresh torques: {data.torques}")
        """
        return self._relay.snapshot()

    def _set_event_sink(self, sink: Callable[[TorqueData], None]) -> None:
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
        raw_torques = list(msg.data[1:])

        if len(raw_torques) != len(expected_fields):
            return

        decoded = [v * 100 / 255 for v in raw_torques]
        self._pending[cmd] = decoded

        # Check if all frames have been received
        if set(self._pending.keys()) != set(self._FRAME_MAP.keys()):
            return

        # All frames received — merge into L20liteTorque
        kwargs: dict[str, float] = {}
        for frame_cmd, fields in self._FRAME_MAP.items():
            for field, value in zip(fields, self._pending[frame_cmd]):
                kwargs[field] = value

        torques = L20liteTorque(**kwargs)
        torque_data = TorqueData(torques=torques, timestamp=time.time())
        self._in_flight = False
        self._pending.clear()
        self._relay.push(torque_data)
