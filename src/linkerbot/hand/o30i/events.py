"""Unified polling and stream types for O30i runtime data."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .acceleration import O30iAccelerationData
from .angle import O30iAngleData
from .current import O30iCurrentData
from .fault import O30iFaultData
from .motion_time import O30iMotionTimeData
from .speed import O30iSpeedData
from .temperature import O30iTemperatureData
from .torque import O30iTorqueData
from .voltage import O30iVoltageData


@dataclass(frozen=True, slots=True)
class AngleEvent:
    data: O30iAngleData


@dataclass(frozen=True, slots=True)
class SpeedEvent:
    data: O30iSpeedData


@dataclass(frozen=True, slots=True)
class AccelerationEvent:
    data: O30iAccelerationData


@dataclass(frozen=True, slots=True)
class CurrentEvent:
    data: O30iCurrentData


@dataclass(frozen=True, slots=True)
class VoltageEvent:
    data: O30iVoltageData


@dataclass(frozen=True, slots=True)
class TorqueEvent:
    data: O30iTorqueData


@dataclass(frozen=True, slots=True)
class TemperatureEvent:
    data: O30iTemperatureData


@dataclass(frozen=True, slots=True)
class MotionTimeEvent:
    data: O30iMotionTimeData


@dataclass(frozen=True, slots=True)
class FaultEvent:
    data: O30iFaultData


SensorEvent = (
    AngleEvent
    | SpeedEvent
    | AccelerationEvent
    | CurrentEvent
    | VoltageEvent
    | TorqueEvent
    | TemperatureEvent
    | MotionTimeEvent
    | FaultEvent
)


class SensorSource(str, Enum):
    ANGLE = "angle"
    SPEED = "speed"
    ACCELERATION = "acceleration"
    CURRENT = "current"
    VOLTAGE = "voltage"
    TORQUE = "torque"
    TEMPERATURE = "temperature"
    MOTION_TIME = "motion_time"
    FAULT = "fault"


@dataclass(frozen=True, slots=True)
class O30iSnapshot:
    angle: O30iAngleData | None
    speed: O30iSpeedData | None
    acceleration: O30iAccelerationData | None
    current: O30iCurrentData | None
    voltage: O30iVoltageData | None
    torque: O30iTorqueData | None
    temperature: O30iTemperatureData | None
    motion_time: O30iMotionTimeData | None
    fault: O30iFaultData | None
    timestamp: float
