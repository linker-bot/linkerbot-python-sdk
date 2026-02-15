"""Torque control and sensing for O6 robotic hand.

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


@dataclass
class O6Torque:
    """Joint torques for O6 hand (0-100 range or milliamps).

    Torques can be specified either as normalized 0-100 values or in milliamp units.
    Maximum torque: 1657.5 mA (corresponds to 100).

    Attributes:
        thumb_flex: Thumb flexion joint torque (0-100). Higher values = higher torque limit.
        thumb_abd: Thumb abduction joint torque (0-100). Higher values = higher torque limit.
        index: Index finger flexion joint torque (0-100). Higher values = higher torque limit.
        middle: Middle finger flexion joint torque (0-100). Higher values = higher torque limit.
        ring: Ring finger flexion joint torque (0-100). Higher values = higher torque limit.
        pinky: Pinky finger flexion joint torque (0-100). Higher values = higher torque limit.
    """

    thumb_flex: float
    thumb_abd: float
    index: float
    middle: float
    ring: float
    pinky: float

    # Hardware conversion constant: 1 hardware unit = 6.5 mA
    _MA_PER_UNIT: float = 6.5
    _MAX_MA: float = 255 * _MA_PER_UNIT  # 1657.5 mA

    def to_list(self) -> list[float]:
        """Convert to list of floats in joint order.

        Returns:
            List of 6 joint torques [thumb_flex, thumb_abd, index, middle, ring, pinky]
        """
        return [
            self.thumb_flex,
            self.thumb_abd,
            self.index,
            self.middle,
            self.ring,
            self.pinky,
        ]

    @classmethod
    def from_list(cls, values: list[float]) -> "O6Torque":
        """Construct from list of floats (0-100 range).

        Args:
            values: List of 6 float values in 0-100 range

        Returns:
            O6Torque instance

        Raises:
            ValueError: If list doesn't have exactly 6 elements
        """
        if len(values) != 6:
            raise ValueError(f"Expected 6 values, got {len(values)}")
        for value in values:
            if not isinstance(value, (float, int)):
                raise ValueError(f"Torque value {value} must be float/int")
            if value < 0 or value > 100:
                raise ValueError(f"Value {value} out of range [0, 100]")
        return cls(
            thumb_flex=values[0],
            thumb_abd=values[1],
            index=values[2],
            middle=values[3],
            ring=values[4],
            pinky=values[5],
        )

    def to_raw(self) -> list[int]:
        # Internal: Convert to hardware communication format
        # Use round() for better precision and clamp to valid range [0, 255]
        return [max(0, min(255, round(v * 255 / 100))) for v in self.to_list()]

    @classmethod
    def from_raw(cls, values: list[int]) -> "O6Torque":
        # Internal: Construct from hardware communication format
        if len(values) != 6:
            raise ValueError(f"Expected 6 values, got {len(values)}")
        for value in values:
            if value < 0 or value > 255:
                raise ValueError(f"Value {value} out of range [0, 255]")
        normalized = [v * 100 / 255 for v in values]
        return cls.from_list(normalized)

    def to_milliamps(self) -> list[float]:
        """Convert to list of torques in milliamp units.

        Returns:
            List of 6 joint torques in mA [thumb_flex, thumb_abd, index, middle, ring, pinky]

        Example:
            >>> torque = O6Torque(50.0, 50.0, 50.0, 50.0, 50.0, 50.0)
            >>> ma_values = torque.to_milliamps()
            >>> print(ma_values[0])  # ~828.75 mA
        """
        return [v * self._MAX_MA / 100 for v in self.to_list()]

    @classmethod
    def from_milliamps(cls, ma_values: list[float]) -> "O6Torque":
        """Construct from list of torques in milliamp units.

        Args:
            ma_values: List of 6 torque values in milliamps (0 to 1657.5 mA)

        Returns:
            O6Torque instance

        Raises:
            ValueError: If list doesn't have exactly 6 elements or values are out of range.

        Example:
            >>> # Set all joints to 800 mA
            >>> torque = O6Torque.from_milliamps([800.0, 800.0, 800.0, 800.0, 800.0, 800.0])
            >>> # Set different torques per joint
            >>> torque = O6Torque.from_milliamps([1000.0, 800.0, 1200.0, 1200.0, 1200.0, 1200.0])
        """
        if len(ma_values) != 6:
            raise ValueError(f"Expected 6 values, got {len(ma_values)}")

        # Validate milliamp values
        for i, ma in enumerate(ma_values):
            if ma < 0 or ma > cls._MAX_MA:
                raise ValueError(
                    f"Milliamp value {i} ({ma}) out of range [0, {cls._MAX_MA:.2f}]"
                )

        # Convert mA to 0-100 range
        normalized = [ma * 100 / cls._MAX_MA for ma in ma_values]
        return cls.from_list(normalized)

    def __getitem__(self, index: int) -> float:
        """Support indexing: torques[0] returns thumb_flex.

        Args:
            index: Joint index (0-5)

        Returns:
            Joint torque value

        Raises:
            IndexError: If index is out of range
        """
        return self.to_list()[index]

    def __len__(self) -> int:
        """Return number of joints (always 6 for O6)."""
        return 6


@dataclass(frozen=True)
class TorqueData:
    """Immutable torque data container.

    Attributes:
        torques: O6Torque instance containing joint torques (0-100 range).
        timestamp: Unix timestamp when the data was received.
    """

    torques: O6Torque
    timestamp: float


class TorqueManager:
    """Manager for joint torque control and sensing.

    This class provides three access modes for torque operations:
    1. Torque control: set_torques() - send 6 target torques and cache response
    2. Blocking mode: get_blocking() - request and wait for 6 current torques
    3. Cache reading: get_snapshot() - non-blocking read of cached torques
    """

    _CONTROL_CMD = 0x02
    _SENSE_CMD = [0x02]
    _TORQUE_COUNT = 6

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

    def set_torques(self, torques: O6Torque | list[float]) -> None:
        """Send target torques to the robotic hand.

        Args:
            torques: O6Torque instance or list of 6 target torques (range 0-100 each).

        Raises:
            ValidationError: If torques count is not 6 or values are out of range.

        Example:
            >>> manager.set_torques(O6Torque(thumb_flex=50.0, thumb_abd=30.0,
            ...                              index=60.0, middle=60.0, ring=60.0, pinky=60.0))
            >>> manager.set_torques([50.0, 30.0, 60.0, 60.0, 60.0, 60.0])
        """
        if isinstance(torques, O6Torque):
            raw_torques = torques.to_raw()
        elif isinstance(torques, list):
            raw_torques = O6Torque.from_list(torques).to_raw()
        else:
            raise ValidationError(
                f"Expected O6Torque or list, got {type(torques).__name__}"
            )

        # Build and send message
        data = [self._CONTROL_CMD, *raw_torques]
        msg = can.Message(
            arbitration_id=self._arbitration_id,
            data=data,
            is_extended_id=False,
        )
        self._dispatcher.send(msg)

    def get_blocking(self, timeout_ms: float = 100) -> TorqueData:
        """Request and wait for current joint torques (blocking).

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

    def _send_sense_request(self) -> None:
        msg = can.Message(
            arbitration_id=self._arbitration_id,
            data=self._SENSE_CMD,
            is_extended_id=False,
        )
        self._dispatcher.send(msg)

    def _on_message(self, msg: can.Message) -> None:
        if msg.arbitration_id != self._arbitration_id:
            return

        if len(msg.data) < 2 or msg.data[0] != self._CONTROL_CMD:
            return

        raw_torques = list(msg.data[1:])

        if len(raw_torques) != self._TORQUE_COUNT:
            return

        torques = O6Torque.from_raw(raw_torques)
        torque_data = TorqueData(torques=torques, timestamp=time.time())
        self._relay.push(torque_data)
