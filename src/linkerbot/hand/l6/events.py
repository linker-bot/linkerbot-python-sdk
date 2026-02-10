"""Unified event types for L6 sensor data streaming.

This module defines the event types used by L6.stream() for delivering
sensor data as a tagged union, enabling match-case dispatching.
"""

from dataclasses import dataclass
from enum import Enum

from .angle import AngleData
from .current import CurrentData
from .fault import FaultData
from .force_sensor import AllFingersData
from .temperature import TemperatureData
from .torque import TorqueData


@dataclass(frozen=True)
class AngleEvent:
    data: AngleData


@dataclass(frozen=True)
class TorqueEvent:
    data: TorqueData


@dataclass(frozen=True)
class TemperatureEvent:
    data: TemperatureData


@dataclass(frozen=True)
class CurrentEvent:
    data: CurrentData


@dataclass(frozen=True)
class FaultEvent:
    data: FaultData


@dataclass(frozen=True)
class ForceSensorEvent:
    data: AllFingersData


SensorEvent = (
    AngleEvent
    | TorqueEvent
    | TemperatureEvent
    | CurrentEvent
    | FaultEvent
    | ForceSensorEvent
)


class SensorSource(str, Enum):
    """Sensor source identifier for start_polling() sources parameter."""

    ANGLE = "angle"
    TORQUE = "torque"
    TEMPERATURE = "temperature"
    CURRENT = "current"
    FAULT = "fault"
    FORCE_SENSOR = "force_sensor"


@dataclass(frozen=True)
class L6Snapshot:
    """Complete snapshot of all sensor data at a point in time."""

    angle: AngleData | None
    torque: TorqueData | None
    temperature: TemperatureData | None
    current: CurrentData | None
    fault: FaultData | None
    force_sensor: AllFingersData | None
    timestamp: float
