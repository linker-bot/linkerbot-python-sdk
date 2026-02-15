"""Unified event types for L20Lite sensor data streaming.

This module defines the event types used by L20Lite.stream() for delivering
sensor data as a tagged union, enabling match-case dispatching.
"""

from dataclasses import dataclass
from enum import Enum

from .angle import AngleData
from .force_sensor import AllFingersData
from .speed import SpeedData
from .temperature import TemperatureData
from .torque import TorqueData


@dataclass(frozen=True)
class AngleEvent:
    data: AngleData


@dataclass(frozen=True)
class SpeedEvent:
    data: SpeedData


@dataclass(frozen=True)
class TorqueEvent:
    data: TorqueData


@dataclass(frozen=True)
class TemperatureEvent:
    data: TemperatureData


@dataclass(frozen=True)
class ForceSensorEvent:
    data: AllFingersData


SensorEvent = (
    AngleEvent | SpeedEvent | TorqueEvent | TemperatureEvent | ForceSensorEvent
)


class SensorSource(str, Enum):
    """Sensor source identifier for start_polling() sources parameter."""

    ANGLE = "angle"
    SPEED = "speed"
    TORQUE = "torque"
    TEMPERATURE = "temperature"
    FORCE_SENSOR = "force_sensor"


@dataclass(frozen=True)
class L20liteSnapshot:
    """Complete snapshot of all sensor data at a point in time."""

    angle: AngleData | None
    speed: SpeedData | None
    torque: TorqueData | None
    temperature: TemperatureData | None
    force_sensor: AllFingersData | None
    timestamp: float
