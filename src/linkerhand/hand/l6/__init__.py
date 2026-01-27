"""L6 robotic hand control package.

This package provides the L6 interface for controlling the L6 robotic hand
via CAN bus communication.
"""

from .angle import AngleData, L6Angle
from .current import CurrentData, CurrentManager, L6Current
from .device_id import DeviceIDManager, DeviceIDs
from .factory_reset import FactoryResetManager
from .fault import FaultCode, FaultData, FaultManager, L6Fault
from .force_sensor import ForceSensorData, ForceSensorManager
from .l6 import L6
from .limit_compensation import (
    L6LimitCompensation,
    LimitCompensationData,
    LimitCompensationManager,
)
from .speed import L6Speed
from .stall import L6StallThreshold, L6StallTime, L6StallTorque, StallManager
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
    "StallManager",
    "VersionManager",
    "LimitCompensationManager",
    "DeviceIDManager",
    "FactoryResetManager",
    # Data containers
    "AngleData",
    "TorqueData",
    "ForceSensorData",
    "TemperatureData",
    "CurrentData",
    "FaultData",
    "DeviceIDs",
    "DeviceInfo",
    "LimitCompensationData",
    # Type classes
    "L6Angle",
    "L6Torque",
    "L6Speed",
    "L6Temperature",
    "L6Current",
    "L6Fault",
    "L6StallTime",
    "L6StallThreshold",
    "L6StallTorque",
    "L6LimitCompensation",
    "FaultCode",
    "Version",
]
