"""L20Lite robotic hand control package.

This package provides the L20Lite interface for controlling the L20Lite robotic hand
via CAN bus communication.
"""

from .angle import AngleData, L20liteAngle
from .events import (
    AngleEvent,
    ForceSensorEvent,
    L20liteSnapshot,
    SensorEvent,
    SensorSource,
    SpeedEvent,
    TemperatureEvent,
    TorqueEvent,
)
from .fault import FaultCode, FaultData, FaultManager, L20liteFault
from .force_sensor import AllFingersData, ForceSensorData, ForceSensorManager
from .l20lite import L20lite
from .speed import L20liteSpeed, SpeedData
from .temperature import L20liteTemperature, TemperatureData, TemperatureManager
from .torque import L20liteTorque, TorqueData
from .version import DeviceInfo, Version, VersionManager

__all__ = [
    "L20lite",
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
    "L20liteSnapshot",
    # Event types
    "AngleEvent",
    "SpeedEvent",
    "TorqueEvent",
    "TemperatureEvent",
    "ForceSensorEvent",
    "SensorEvent",
    "SensorSource",
    # Type classes
    "L20liteAngle",
    "L20liteSpeed",
    "L20liteTorque",
    "L20liteTemperature",
    "L20liteFault",
    "FaultCode",
    "Version",
]
