"""Unified event types for L25 sensor data streaming.

This module defines the event types used by L25.stream() for delivering
sensor data as a tagged union, enabling match-case dispatching.
"""

from dataclasses import dataclass
from enum import Enum

from .angle import AngleData
from .fault import FaultData
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
class FaultEvent:
    data: FaultData


@dataclass(frozen=True)
class ForceSensorEvent:
    data: AllFingersData


SensorEvent = (
    AngleEvent
    | SpeedEvent
    | TorqueEvent
    | TemperatureEvent
    | FaultEvent
    | ForceSensorEvent
)


class SensorSource(str, Enum):
    """Sensor source identifier for start_polling() sources parameter."""

    ANGLE = "angle"
    SPEED = "speed"
    TORQUE = "torque"
    TEMPERATURE = "temperature"
    FAULT = "fault"
    FORCE_SENSOR = "force_sensor"


@dataclass(frozen=True)
class L25Snapshot:
    """Complete snapshot of all sensor data at a point in time."""

    angle: AngleData | None
    speed: SpeedData | None
    torque: TorqueData | None
    temperature: TemperatureData | None
    fault: FaultData | None
    force_sensor: AllFingersData | None
    timestamp: float
