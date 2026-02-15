"""Temperature sensing for L25 robotic hand.

This module provides the TemperatureManager class for reading motor temperature
sensor data via CAN bus communication. L25 has 16 temperature sensors
split across five CAN frames (0x61-0x65), one per finger.
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
class L25Temperature:
    """Motor temperatures for L25 hand in degrees Celsius (°C).

    Attributes:
        thumb_abd: Thumb abduction motor temperature in °C
        thumb_yaw: Thumb yaw motor temperature in °C
        thumb_root1: Thumb root1 motor temperature in °C
        thumb_tip: Thumb tip motor temperature in °C
        index_abd: Index finger abduction motor temperature in °C
        index_root1: Index finger root1 motor temperature in °C
        index_tip: Index finger tip motor temperature in °C
        middle_abd: Middle finger abduction motor temperature in °C
        middle_root1: Middle finger root1 motor temperature in °C
        middle_tip: Middle finger tip motor temperature in °C
        ring_abd: Ring finger abduction motor temperature in °C
        ring_root1: Ring finger root1 motor temperature in °C
        ring_tip: Ring finger tip motor temperature in °C
        pinky_abd: Pinky finger abduction motor temperature in °C
        pinky_root1: Pinky finger root1 motor temperature in °C
        pinky_tip: Pinky finger tip motor temperature in °C
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
            List of 16 temperatures in °C in order: thumb_abd, thumb_yaw,
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

    def to_raw(self) -> list[int]:
        # Internal: Convert to hardware communication format
        return [int(v) for v in self.to_list()]

    @classmethod
    def from_list(cls, values: list[float]) -> "L25Temperature":
        """Construct from list of floats in degrees Celsius.

        Args:
            values: List of 16 float values in °C

        Returns:
            L25Temperature instance

        Raises:
            ValueError: If list doesn't have exactly 16 elements
        """
        if len(values) != _JOINT_COUNT:
            raise ValueError(f"Expected {_JOINT_COUNT} values, got {len(values)}")
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

    @classmethod
    def from_raw(cls, values: list[int]) -> "L25Temperature":
        # Internal: Construct from hardware communication format
        if len(values) != _JOINT_COUNT:
            raise ValueError(f"Expected {_JOINT_COUNT} values, got {len(values)}")
        for value in values:
            if value < 0 or value > 255:
                raise ValueError(f"Value {value} out of range [0, 255]")
        temperatures_celsius = [float(v) for v in values]
        return cls.from_list(temperatures_celsius)

    def __getitem__(self, index: int) -> float:
        """Support indexing: temperatures[0] returns thumb_abd (abduction).

        Args:
            index: Joint index (0-15)

        Returns:
            Temperature value

        Raises:
            IndexError: If index is out of range
        """
        return self.to_list()[index]

    def __len__(self) -> int:
        """Return number of temperature sensors (always 16 for L25)."""
        return _JOINT_COUNT


@dataclass(frozen=True)
class TemperatureData:
    """Immutable temperature data container.

    Attributes:
        temperatures: L25Temperature instance containing motor temperatures in degrees Celsius (°C).
        timestamp: Unix timestamp when the data was received.
    """

    temperatures: L25Temperature
    timestamp: float


class TemperatureManager:
    """Manager for motor temperature sensing.

    L25 splits 16 temperature sensors across five CAN frames, one per finger:
    - 0x61: thumb (abd, yaw, root1, reserve, reserve, tip)
    - 0x62: index (abd, reserve, root1, reserve, reserve, tip)
    - 0x63: middle (abd, reserve, root1, reserve, reserve, tip)
    - 0x64: ring (abd, reserve, root1, reserve, reserve, tip)
    - 0x65: pinky (abd, reserve, root1, reserve, reserve, tip)

    Each frame is 7 bytes: [cmd, abd, yaw/reserve, root1, reserve, reserve, tip].
    Reserved positions (None in the map) are ignored on decode.

    This class provides two access modes for temperature operations:
    1. Blocking mode: get_blocking() - request and wait for all 16 temperatures
    2. Cache reading: get_snapshot() - non-blocking read of cached temperatures
    """

    _FRAME_MAP: dict[int, list[str | None]] = {
        0x61: ["thumb_abd", "thumb_yaw", "thumb_root1", None, None, "thumb_tip"],
        0x62: ["index_abd", None, "index_root1", None, None, "index_tip"],
        0x63: ["middle_abd", None, "middle_root1", None, None, "middle_tip"],
        0x64: ["ring_abd", None, "ring_root1", None, None, "ring_tip"],
        0x65: ["pinky_abd", None, "pinky_root1", None, None, "pinky_tip"],
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

        This method sends sensing requests for all five frames and blocks until
        all 16 temperatures are received or the timeout expires.

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

        # All frames received — merge into L25Temperature
        kwargs: dict[str, float] = {}
        for frame_cmd, fields in self._FRAME_MAP.items():
            for field, value in zip(fields, self._pending[frame_cmd]):
                if field is not None:
                    kwargs[field] = value

        temperatures = L25Temperature(**kwargs)
        temp_data = TemperatureData(temperatures=temperatures, timestamp=time.time())
        self._in_flight = False
        self._pending.clear()
        self._relay.push(temp_data)
