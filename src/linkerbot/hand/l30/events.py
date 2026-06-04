"""Unified event types for L30 sensor data streaming."""

from dataclasses import dataclass
from enum import Enum

from .angle import AngleData
from .current import CurrentData
from .fault import FaultData
from .force_sensor import AllFingersData
from .speed import SpeedData
from .temperature import TemperatureData
from .torque import TorqueData


@dataclass(frozen=True, slots=True)
class AngleEvent:
    """Unified stream event carrying updated angle data.

    Attributes:
        data: AngleData produced by a blocking read, poll, or periodic report.
    """

    data: AngleData


@dataclass(frozen=True, slots=True)
class SpeedEvent:
    """Unified stream event carrying updated speed data.

    Attributes:
        data: SpeedData produced by a blocking read, poll, or periodic report.
    """

    data: SpeedData


@dataclass(frozen=True, slots=True)
class TorqueEvent:
    """Unified stream event carrying the latest commanded torque targets.

    Attributes:
        data: TorqueData produced when a torque command updates the cache.
    """

    data: TorqueData


@dataclass(frozen=True, slots=True)
class CurrentEvent:
    """Unified stream event carrying updated current data.

    Attributes:
        data: CurrentData produced by a blocking read, poll, or periodic report.
    """

    data: CurrentData


@dataclass(frozen=True, slots=True)
class TemperatureEvent:
    """Unified stream event carrying updated temperature data.

    Attributes:
        data: TemperatureData produced by a blocking read, poll, or periodic report.
    """

    data: TemperatureData


@dataclass(frozen=True, slots=True)
class FaultEvent:
    """Unified stream event carrying updated fault status data.

    Attributes:
        data: FaultData produced by a blocking read, poll, or periodic report.
    """

    data: FaultData


@dataclass(frozen=True, slots=True)
class ForceSensorEvent:
    """Unified stream event carrying updated all-finger tactile data.

    Attributes:
        data: AllFingersData produced by an all-finger tactile read.
    """

    data: AllFingersData


SensorEvent = (
    AngleEvent
    | SpeedEvent
    | TorqueEvent
    | CurrentEvent
    | TemperatureEvent
    | FaultEvent
    | ForceSensorEvent
)


class SensorSource(str, Enum):
    """Sensor source names accepted by L30 host-side polling."""

    ANGLE = "angle"
    SPEED = "speed"
    CURRENT = "current"
    TEMPERATURE = "temperature"
    FAULT = "fault"
    FORCE_SENSOR = "force_sensor"


@dataclass(frozen=True, slots=True)
class L30Snapshot:
    """Non-blocking aggregate snapshot of cached L30 data.

    Attributes:
        angle: Latest angle data, or None if no angle data has been received.
        speed: Latest speed data, or None if no speed data has been received.
        torque: Latest commanded torque target, or None if none has been sent.
        current: Latest current data, or None if no current data has been received.
        temperature: Latest temperature data, or None if no temperature data has
            been received.
        fault: Latest fault status data, or None if no fault data has been received.
        force_sensor: Latest all-finger tactile data, or None if no all-finger
            tactile read has completed.
        timestamp: Unix timestamp when the aggregate snapshot was created.
    """

    angle: AngleData | None
    speed: SpeedData | None
    torque: TorqueData | None
    current: CurrentData | None
    temperature: TemperatureData | None
    fault: FaultData | None
    force_sensor: AllFingersData | None
    timestamp: float
