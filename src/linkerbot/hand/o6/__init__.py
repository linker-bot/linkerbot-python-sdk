"""O6 robotic hand control module.

This module provides control interfaces for the O6 robotic hand.
"""

from linkerbot.hand.o6.angle import AngleData, AngleManager, O6Angle
from linkerbot.hand.o6.factory_reset import FactoryResetManager
from linkerbot.hand.o6.fault import FaultCode, FaultData, FaultManager, O6Fault
from linkerbot.hand.o6.force_sensor import (
    AllFingersData,
    ForceSensorData,
    ForceSensorManager,
    SingleForceSensorManager,
)
from linkerbot.hand.o6.o6 import O6
from linkerbot.hand.o6.speed import (
    AccelerationData,
    AccelerationManager,
    O6Acceleration,
    O6Speed,
    SpeedData,
    SpeedManager,
)
from linkerbot.hand.o6.stall import (
    O6StallThreshold,
    O6StallTime,
    O6StallTorque,
    StallManager,
)
from linkerbot.hand.o6.temperature import (
    O6Temperature,
    TemperatureData,
    TemperatureManager,
)
from linkerbot.hand.o6.torque import O6Torque, TorqueData, TorqueManager
from linkerbot.hand.o6.version import DeviceInfo, Version, VersionManager

__all__ = [
    "O6Angle",
    "AngleData",
    "AngleManager",
    "O6Speed",
    "SpeedData",
    "SpeedManager",
    "O6Acceleration",
    "AccelerationData",
    "AccelerationManager",
    "O6Temperature",
    "TemperatureData",
    "TemperatureManager",
    "O6Torque",
    "TorqueData",
    "TorqueManager",
    "O6StallThreshold",
    "O6StallTime",
    "O6StallTorque",
    "StallManager",
    "FaultCode",
    "O6Fault",
    "FaultData",
    "FaultManager",
    "ForceSensorData",
    "AllFingersData",
    "SingleForceSensorManager",
    "ForceSensorManager",
    "Version",
    "DeviceInfo",
    "VersionManager",
    "FactoryResetManager",
    "O6",
]
