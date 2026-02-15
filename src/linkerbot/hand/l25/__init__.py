"""L25 robotic hand control package.

This package provides the L25 interface for controlling the L25 robotic hand
via CAN bus communication.
"""

from .angle import AngleData, L25Angle
from .events import (
    AngleEvent,
    FaultEvent,
    ForceSensorEvent,
    L25Snapshot,
    SensorEvent,
    SensorSource,
    SpeedEvent,
    TemperatureEvent,
    TorqueEvent,
)
from .fault import FaultData, FaultManager, L25Fault, L25FaultCode
from .force_sensor import AllFingersData, ForceSensorData, ForceSensorManager
from .l25 import L25
from .speed import L25Speed, SpeedData
from .temperature import L25Temperature, TemperatureData, TemperatureManager
from .torque import L25Torque, TorqueData
from .version import DeviceInfo, Version, VersionManager

__all__ = [
    "L25",
    # Managers
    "ForceSensorManager",
    "TemperatureManager",
    "FaultManager",
    "VersionManager",
    # Data containers
    "AngleData",
    "SpeedData",
    "TorqueData",
    "ForceSensorData",
    "AllFingersData",
    "TemperatureData",
    "FaultData",
    "DeviceInfo",
    "L25Snapshot",
    # Event types
    "AngleEvent",
    "SpeedEvent",
    "TorqueEvent",
    "TemperatureEvent",
    "FaultEvent",
    "ForceSensorEvent",
    "SensorEvent",
    "SensorSource",
    # Type classes
    "L25Angle",
    "L25Speed",
    "L25Torque",
    "L25Temperature",
    "L25Fault",
    "L25FaultCode",
    "Version",
]
