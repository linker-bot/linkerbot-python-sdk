"""Unified polling and stream types for O30 runtime data."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .acceleration import O30AccelerationData
from .angle import O30AngleData
from .current import O30CurrentData
from .fault import O30FaultData
from .motion_time import O30MotionTimeData
from .speed import O30SpeedData
from .temperature import O30TemperatureData
from .torque import O30TorqueData
from .voltage import O30VoltageData


@dataclass(frozen=True, slots=True)
class AngleEvent:
    data: O30AngleData


@dataclass(frozen=True, slots=True)
class SpeedEvent:
    data: O30SpeedData


@dataclass(frozen=True, slots=True)
class AccelerationEvent:
    data: O30AccelerationData


@dataclass(frozen=True, slots=True)
class CurrentEvent:
    data: O30CurrentData


@dataclass(frozen=True, slots=True)
class VoltageEvent:
    data: O30VoltageData


@dataclass(frozen=True, slots=True)
class TorqueEvent:
    data: O30TorqueData


@dataclass(frozen=True, slots=True)
class TemperatureEvent:
    data: O30TemperatureData


@dataclass(frozen=True, slots=True)
class MotionTimeEvent:
    data: O30MotionTimeData


@dataclass(frozen=True, slots=True)
class FaultEvent:
    data: O30FaultData


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
class O30Snapshot:
    angle: O30AngleData | None
    speed: O30SpeedData | None
    acceleration: O30AccelerationData | None
    current: O30CurrentData | None
    voltage: O30VoltageData | None
    torque: O30TorqueData | None
    temperature: O30TemperatureData | None
    motion_time: O30MotionTimeData | None
    fault: O30FaultData | None
    timestamp: float


# Backward-compatible aliases for the former model name.
O30iAccelerationData = O30AccelerationData
O30iAngleData = O30AngleData
O30iCurrentData = O30CurrentData
O30iFaultData = O30FaultData
O30iMotionTimeData = O30MotionTimeData
O30iSpeedData = O30SpeedData
O30iTemperatureData = O30TemperatureData
O30iTorqueData = O30TorqueData
O30iVoltageData = O30VoltageData
O30iSnapshot = O30Snapshot
