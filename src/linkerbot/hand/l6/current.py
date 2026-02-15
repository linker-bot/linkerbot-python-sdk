"""Current sensing for L6 robotic hand.

This module provides the CurrentManager class for reading motor current
sensor data via CAN bus communication.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass

import can

from linkerbot.comm import CANMessageDispatcher
from linkerbot.exceptions import ValidationError
from linkerbot.relay import DataRelay


@dataclass
class L6Current:
    """Motor currents for L6 hand in milliamps (mA).

    Attributes:
        thumb_flex: Thumb flexion motor current in mA
        thumb_abd: Thumb abduction motor current in mA
        index: Index finger motor current in mA
        middle: Middle finger motor current in mA
        ring: Ring finger motor current in mA
        pinky: Pinky finger motor current in mA
    """

    thumb_flex: float
    thumb_abd: float
    index: float
    middle: float
    ring: float
    pinky: float

    def to_list(self) -> list[float]:
        """Convert to list of floats in joint order.

        Returns:
            List of 6 currents [thumb_flex, thumb_abd, index, middle, ring, pinky]
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
    def from_list(cls, values: list[float]) -> "L6Current":
        """Construct from list of floats in milliamps.

        Args:
            values: List of 6 float values in mA

        Returns:
            L6Current instance

        Raises:
            ValueError: If list doesn't have exactly 6 elements
        """
        if len(values) != 6:
            raise ValueError(f"Expected 6 values, got {len(values)}")
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
        return [round(v * 255 / 1400) for v in self.to_list()]

    @classmethod
    def from_raw(cls, values: list[int]) -> "L6Current":
        # Internal: Construct from hardware communication format
        if len(values) != 6:
            raise ValueError(f"Expected 6 values, got {len(values)}")
        for value in values:
            if value < 0 or value > 255:
                raise ValueError(f"Value {value} out of range [0, 255]")
        currents_mA = [v * 1400 / 255 for v in values]
        return cls.from_list(currents_mA)

    def __getitem__(self, index: int) -> float:
        """Support indexing: currents[0] returns thumb_flex.

        Args:
            index: Joint index (0-5)

        Returns:
            Current value

        Raises:
            IndexError: If index is out of range
        """
        return self.to_list()[index]

    def __len__(self) -> int:
        """Return number of current sensors (always 6 for L6)."""
        return 6


@dataclass(frozen=True)
class CurrentData:
    """Immutable current data container.

    Attributes:
        currents: L6Current instance containing motor currents in milliamps (mA).
        timestamp: Unix timestamp when the data was received.
    """

    currents: L6Current
    timestamp: float


class CurrentManager:
    """Manager for motor current sensing.

    This class provides two access modes for current operations:
    1. Blocking mode: get_blocking() - request and wait for 6 currents
    2. Cache reading: get_snapshot() - non-blocking read of cached currents
    """

    _SENSE_CMD = 0x36
    _SENSE_CMD_DATA = [0x36]
    _CURRENT_COUNT = 6

    def __init__(self, arbitration_id: int, dispatcher: CANMessageDispatcher) -> None:
        """Initialize the current manager.

        Args:
            arbitration_id: CAN arbitration ID for current sensing.
            dispatcher: CAN message dispatcher to use for communication.
        """
        self._arbitration_id = arbitration_id
        self._dispatcher = dispatcher
        self._dispatcher.subscribe(self._on_message)
        self._relay = DataRelay[CurrentData]()

    def get_blocking(self, timeout_ms: float = 100) -> CurrentData:
        """Request and wait for current motor currents (blocking).

        Args:
            timeout_ms: Maximum time to wait in milliseconds (default: 100).

        Returns:
            CurrentData instance containing currents and timestamp.

        Raises:
            TimeoutError: If no response is received within timeout.
            ValidationError: If timeout_ms is not positive.

        Example:
            >>> data = manager.get_blocking(timeout_ms=500)
            >>> print(f"Current currents: {data.currents}")
        """
        if timeout_ms <= 0:
            raise ValidationError("timeout_ms must be positive")
        self._send_sense_request()
        return self._relay.wait(timeout_ms / 1000.0)

    def get_snapshot(self) -> CurrentData | None:
        """Get the most recent cached current data (non-blocking).

        Returns:
            CurrentData instance or None if no data received yet.

        Example:
            >>> data = manager.get_snapshot()
            >>> if data:
            ...     print(f"Fresh currents: {data.currents}")
        """
        return self._relay.snapshot()

    def _set_event_sink(self, sink: Callable[[CurrentData], None]) -> None:
        self._relay.set_sink(sink)

    def _send_sense_request(self) -> None:
        msg = can.Message(
            arbitration_id=self._arbitration_id,
            data=self._SENSE_CMD_DATA,
            is_extended_id=False,
        )
        self._dispatcher.send(msg)

    def _on_message(self, msg: can.Message) -> None:
        if msg.arbitration_id != self._arbitration_id:
            return

        if len(msg.data) < 2 or msg.data[0] != self._SENSE_CMD:
            return

        raw_currents = list(msg.data[1:])

        if len(raw_currents) != self._CURRENT_COUNT:
            return

        currents = L6Current.from_raw(raw_currents)
        current_data = CurrentData(currents=currents, timestamp=time.time())
        self._relay.push(current_data)
