"""Temperature sensing for L20lite robotic hand.

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

_JOINT_COUNT = 10


@dataclass
class L20liteTemperature:
    """Motor temperatures for L20lite hand in degrees Celsius (°C).

    Attributes:
        thumb_flex: Thumb flexion motor temperature in °C
        thumb_abd: Thumb abduction motor temperature in °C
        index_flex: Index finger flexion motor temperature in °C
        middle_flex: Middle finger flexion motor temperature in °C
        ring_flex: Ring finger flexion motor temperature in °C
        pinky_flex: Pinky finger flexion motor temperature in °C
        index_abd: Index finger abduction motor temperature in °C
        ring_abd: Ring finger abduction motor temperature in °C
        pinky_abd: Pinky finger abduction motor temperature in °C
        thumb_yaw: Thumb yaw motor temperature in °C
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
            List of 10 temperatures in °C in order: thumb_flex, thumb_abd,
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

    def to_raw(self) -> list[int]:
        # Internal: Convert to hardware communication format
        return [int(v) for v in self.to_list()]

    @classmethod
    def from_list(cls, values: list[float]) -> "L20liteTemperature":
        """Construct from list of floats in degrees Celsius.

        Args:
            values: List of 10 float values in °C

        Returns:
            L20liteTemperature instance

        Raises:
            ValueError: If list doesn't have exactly 10 elements
        """
        if len(values) != _JOINT_COUNT:
            raise ValueError(f"Expected {_JOINT_COUNT} values, got {len(values)}")
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

    @classmethod
    def from_raw(cls, values: list[int]) -> "L20liteTemperature":
        # Internal: Construct from hardware communication format
        if len(values) != _JOINT_COUNT:
            raise ValueError(f"Expected {_JOINT_COUNT} values, got {len(values)}")
        for value in values:
            if value < 0 or value > 255:
                raise ValueError(f"Value {value} out of range [0, 255]")
        temperatures_celsius = [float(v) for v in values]
        return cls.from_list(temperatures_celsius)

    def __getitem__(self, index: int) -> float:
        """Support indexing: temperatures[0] returns thumb_flex.

        Args:
            index: Joint index (0-9)

        Returns:
            Temperature value

        Raises:
            IndexError: If index is out of range
        """
        return self.to_list()[index]

    def __len__(self) -> int:
        """Return number of temperature sensors (always 10 for L20lite)."""
        return _JOINT_COUNT


@dataclass(frozen=True)
class TemperatureData:
    """Immutable temperature data container.

    Attributes:
        temperatures: L20liteTemperature instance containing motor temperatures in degrees Celsius (°C).
        timestamp: Unix timestamp when the data was received.
    """

    temperatures: L20liteTemperature
    timestamp: float


class TemperatureManager:
    """Manager for motor temperature sensing.

    This class provides two access modes for temperature operations:
    1. Blocking mode: get_blocking() - request and wait for all 10 temperatures
    2. Cache reading: get_snapshot() - non-blocking read of cached temperatures
    """

    _FRAME_MAP: dict[int, list[str]] = {
        0x33: [
            "thumb_flex",
            "thumb_abd",
            "index_flex",
            "middle_flex",
            "ring_flex",
        ],
        0x34: ["pinky_flex", "index_abd", "ring_abd", "pinky_abd", "thumb_yaw"],
    }

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
        self._pending: dict[int, list[float]] = {}
        self._in_flight = False
        self._in_flight_since: float = 0

    def get_blocking(self, timeout_ms: float = 100) -> TemperatureData:
        """Request and wait for current motor temperatures (blocking).

        This method sends a sensing request and blocks until
        all 10 temperatures are received or the timeout expires.

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
        self._pending.clear()
        self._in_flight = False
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
        raw_temperatures = list(msg.data[1:])

        if len(raw_temperatures) != len(expected_fields):
            return

        decoded = [float(v) for v in raw_temperatures]
        self._pending[cmd] = decoded

        # Check if all frames have been received
        if set(self._pending.keys()) != set(self._FRAME_MAP.keys()):
            return

        # All frames received — merge into L20liteTemperature
        kwargs: dict[str, float] = {}
        for frame_cmd, fields in self._FRAME_MAP.items():
            for field, value in zip(fields, self._pending[frame_cmd]):
                kwargs[field] = value

        temperatures = L20liteTemperature(**kwargs)
        temp_data = TemperatureData(temperatures=temperatures, timestamp=time.time())
        self._in_flight = False
        self._pending.clear()
        self._relay.push(temp_data)
