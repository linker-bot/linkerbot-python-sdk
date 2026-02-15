"""L6 robotic hand control package.

This package provides the L6 interface for controlling the L6 robotic hand
via CAN bus communication.
"""

from .angle import AngleData, L6Angle
from .current import CurrentData, CurrentManager, L6Current
from .events import (
    AngleEvent,
    CurrentEvent,
    FaultEvent,
    ForceSensorEvent,
    L6Snapshot,
    SensorEvent,
    SensorSource,
    TemperatureEvent,
    TorqueEvent,
)
from .fault import FaultCode, FaultData, FaultManager, L6Fault
from .force_sensor import AllFingersData, ForceSensorData, ForceSensorManager
from .l6 import L6
from .speed import L6Speed
from .temperature import L6Temperature, TemperatureData, TemperatureManager
from .torque import L6Torque, TorqueData
from .version import DeviceInfo, Version, VersionManager

__all__ = [
    "L6",
    # Managers
    "ForceSensorManager",
    "TemperatureManager",
    "CurrentManager",
    "FaultManager",
    "VersionManager",
    # Data containers
    "AngleData",
    "TorqueData",
    "ForceSensorData",
    "AllFingersData",
    "TemperatureData",
    "CurrentData",
    "FaultData",
    "DeviceInfo",
    "L6Snapshot",
    # Event types
    "AngleEvent",
    "TorqueEvent",
    "TemperatureEvent",
    "CurrentEvent",
    "FaultEvent",
    "ForceSensorEvent",
    "SensorEvent",
    "SensorSource",
    # Type classes
    "L6Angle",
    "L6Torque",
    "L6Speed",
    "L6Temperature",
    "L6Current",
    "L6Fault",
    "FaultCode",
    "Version",
]
