"""Temperature sensing for O6 robotic hand.

This module provides the TemperatureManager class for reading motor temperature
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
class O6Temperature:
    """Motor temperatures for O6 hand in degrees Celsius (deg C).

    Attributes:
        thumb_flex: Thumb flexion motor temperature in deg C
        thumb_abd: Thumb abduction motor temperature in deg C
        index: Index finger motor temperature in deg C
        middle: Middle finger motor temperature in deg C
        ring: Ring finger motor temperature in deg C
        pinky: Pinky finger motor temperature in deg C
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
            List of 6 temperatures in deg C [thumb_flex, thumb_abd, index, middle, ring, pinky]
        """
        return [
            self.thumb_flex,
            self.thumb_abd,
            self.index,
            self.middle,
            self.ring,
            self.pinky,
        ]

    def to_raw(self) -> list[int]:
        # Internal: Convert to hardware communication format
        return [int(v) for v in self.to_list()]

    @classmethod
    def from_list(cls, values: list[float]) -> "O6Temperature":
        """Construct from list of floats in degrees Celsius.

        Args:
            values: List of 6 float values in deg C

        Returns:
            O6Temperature instance

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

    @classmethod
    def from_raw(cls, values: list[int]) -> "O6Temperature":
        # Internal: Construct from hardware communication format
        if len(values) != 6:
            raise ValueError(f"Expected 6 values, got {len(values)}")
        for value in values:
            if value < 0 or value > 255:
                raise ValueError(f"Value {value} out of range [0, 255]")
        temperatures_celsius = [float(v) for v in values]
        return cls.from_list(temperatures_celsius)

    def __getitem__(self, index: int) -> float:
        """Support indexing: temperatures[0] returns thumb_flex.

        Args:
            index: Joint index (0-5)

        Returns:
            Temperature value

        Raises:
            IndexError: If index is out of range
        """
        return self.to_list()[index]

    def __len__(self) -> int:
        """Return number of temperature sensors (always 6 for O6)."""
        return 6


@dataclass(frozen=True)
class TemperatureData:
    """Immutable temperature data container.

    Attributes:
        temperatures: O6Temperature instance containing motor temperatures in degrees Celsius (deg C).
        timestamp: Unix timestamp when the data was received.
    """

    temperatures: O6Temperature
    timestamp: float


class TemperatureManager:
    """Manager for motor temperature sensing.

    This class provides two access modes for temperature operations:
    1. Blocking mode: get_blocking() - request and wait for 6 temperatures
    2. Cache reading: get_snapshot() - non-blocking read of cached temperatures
    """

    _SENSE_CMD = 0x33
    _SENSE_CMD_DATA = [0x33]
    _TEMPERATURE_COUNT = 6

    def __init__(self, arbitration_id: int, dispatcher: CANMessageDispatcher) -> None:
        """Initialize the temperature manager.

        Args:
            arbitration_id: CAN arbitration ID for temperature sensing.
            dispatcher: CAN message dispatcher to use for communication.
        """
        self._arbitration_id = arbitration_id
        self._dispatcher = dispatcher
        self._dispatcher.subscribe(self._on_message)
        self._relay = DataRelay[TemperatureData]()

    def get_blocking(self, timeout_ms: float = 100) -> TemperatureData:
        """Request and wait for current motor temperatures (blocking).

        Args:
            timeout_ms: Maximum time to wait in milliseconds (default: 100).

        Returns:
            TemperatureData instance containing temperatures and timestamp.

        Raises:
            TimeoutError: If no response is received within timeout.
            ValidationError: If timeout_ms is not positive.

        Example:
            >>> data = manager.get_blocking(timeout_ms=500)
            >>> print(f"Current temperatures: {data.temperatures}")
        """
        if timeout_ms <= 0:
            raise ValidationError("timeout_ms must be positive")
        self._send_sense_request()
        return self._relay.wait(timeout_ms / 1000.0)

    def get_snapshot(self) -> TemperatureData | None:
        """Get the most recent cached temperature data (non-blocking).

        Returns:
            TemperatureData instance or None if no data received yet.

        Example:
            >>> data = manager.get_snapshot()
            >>> if data:
            ...     print(f"Fresh temperatures: {data.temperatures}")
        """
        return self._relay.snapshot()

    def _set_event_sink(self, sink: Callable[[TemperatureData], None]) -> None:
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

        raw_temperatures = list(msg.data[1:])

        if len(raw_temperatures) != self._TEMPERATURE_COUNT:
            return

        temperatures = O6Temperature.from_raw(raw_temperatures)
        temp_data = TemperatureData(temperatures=temperatures, timestamp=time.time())
        self._relay.push(temp_data)
