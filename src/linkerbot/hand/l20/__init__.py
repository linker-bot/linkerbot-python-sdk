"""L20 robotic hand control package.

This package provides the L20 interface for controlling the L20 robotic hand
via CAN bus communication.
"""

from .angle import AngleData, L20Angle
from .events import (
    AngleEvent,
    FaultEvent,
    ForceSensorEvent,
    L20Snapshot,
    SensorEvent,
    SensorSource,
    SpeedEvent,
    TemperatureEvent,
    TorqueEvent,
)
from .fault import FaultData, FaultManager, L20Fault, L20FaultCode
from .force_sensor import AllFingersData, ForceSensorData, ForceSensorManager
from .l20 import L20
from .speed import L20Speed, SpeedData
from .temperature import L20Temperature, TemperatureData, TemperatureManager
from .torque import L20Torque, TorqueData
from .version import DeviceInfo, Version, VersionManager

__all__ = [
    "L20",
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
    "L20Snapshot",
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
    "L20Angle",
    "L20Speed",
    "L20Torque",
    "L20Temperature",
    "L20Fault",
    "L20FaultCode",
    "Version",
]
