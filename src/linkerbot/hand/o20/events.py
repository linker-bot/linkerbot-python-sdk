"""Unified event types for O20 sensor data streaming."""

from dataclasses import dataclass
from enum import Enum

from .angle import O20AngleData
from .current import O20CurrentData
from .fault import O20FaultData
from .force_sensor import O20AllFingersData
from .speed import O20SpeedData
from .temperature import O20TemperatureData
from .torque import O20TorqueData


@dataclass(frozen=True, slots=True)
class AngleEvent:
    """Unified stream event carrying updated angle data.

    Attributes:
        data: O20AngleData produced by a blocking read or host-side poll.
    """

    data: O20AngleData


@dataclass(frozen=True, slots=True)
class SpeedEvent:
    """Unified stream event carrying updated speed data.

    Attributes:
        data: O20SpeedData produced by a blocking read or host-side poll.
    """

    data: O20SpeedData


@dataclass(frozen=True, slots=True)
class TorqueEvent:
    """Unified stream event carrying the latest commanded torque targets.

    Attributes:
        data: O20TorqueData produced when a torque command updates the cache.
    """

    data: O20TorqueData


@dataclass(frozen=True, slots=True)
class CurrentEvent:
    """Unified stream event carrying updated current data.

    Attributes:
        data: O20CurrentData produced by a blocking read or host-side poll.
    """

    data: O20CurrentData


@dataclass(frozen=True, slots=True)
class TemperatureEvent:
    """Unified stream event carrying updated temperature data.

    Attributes:
        data: O20TemperatureData produced by a blocking read or host-side poll.
    """

    data: O20TemperatureData


@dataclass(frozen=True, slots=True)
class FaultEvent:
    """Unified stream event carrying updated fault status data.

    Attributes:
        data: O20FaultData produced by a blocking read or host-side poll.
    """

    data: O20FaultData


@dataclass(frozen=True, slots=True)
class ForceSensorEvent:
    """Unified stream event carrying updated all-finger tactile data.

    Attributes:
        data: O20AllFingersData produced by an all-finger tactile read.
    """

    data: O20AllFingersData


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
    """Sensor source names accepted by O20 host-side polling."""

    ANGLE = "angle"
    SPEED = "speed"
    CURRENT = "current"
    TEMPERATURE = "temperature"
    FAULT = "fault"
    FORCE_SENSOR = "force_sensor"


@dataclass(frozen=True, slots=True)
class O20Snapshot:
    """Non-blocking aggregate snapshot of cached O20 data.

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

    angle: O20AngleData | None
    speed: O20SpeedData | None
    torque: O20TorqueData | None
    current: O20CurrentData | None
    temperature: O20TemperatureData | None
    fault: O20FaultData | None
    force_sensor: O20AllFingersData | None
    timestamp: float
