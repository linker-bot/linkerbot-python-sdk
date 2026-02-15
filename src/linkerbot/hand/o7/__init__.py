"""O7 robotic hand control package.

This package provides the O7 interface for controlling the O7 robotic hand
via CAN bus communication.
"""

from linkerbot.hand.o7.angle import AngleData, O7Angle
from linkerbot.hand.o7.events import (
    AccelerationEvent,
    AngleEvent,
    FaultEvent,
    ForceSensorEvent,
    O7Snapshot,
    SensorEvent,
    SensorSource,
    SpeedEvent,
    TemperatureEvent,
    TorqueEvent,
)
from linkerbot.hand.o7.fault import FaultCode, FaultData, FaultManager, O7Fault
from linkerbot.hand.o7.force_sensor import (
    AllFingersData,
    ForceSensorData,
    ForceSensorManager,
    SingleForceSensorManager,
)
from linkerbot.hand.o7.o7 import O7
from linkerbot.hand.o7.speed import (
    AccelerationData,
    AccelerationManager,
    O7Acceleration,
    O7Speed,
    SpeedData,
    SpeedManager,
)
from linkerbot.hand.o7.temperature import (
    O7Temperature,
    TemperatureData,
    TemperatureManager,
)
from linkerbot.hand.o7.torque import O7Torque, TorqueData, TorqueManager
from linkerbot.hand.o7.version import DeviceInfo, Version, VersionManager

__all__ = [
    "O7",
    # Managers
    "ForceSensorManager",
    "SingleForceSensorManager",
    "TemperatureManager",
    "FaultManager",
    "VersionManager",
    "AccelerationManager",
    "SpeedManager",
    "TorqueManager",
    # Data containers
    "AngleData",
    "TorqueData",
    "SpeedData",
    "AccelerationData",
    "ForceSensorData",
    "AllFingersData",
    "TemperatureData",
    "FaultData",
    "O7Snapshot",
    # Event types
    "AngleEvent",
    "TorqueEvent",
    "SpeedEvent",
    "AccelerationEvent",
    "TemperatureEvent",
    "FaultEvent",
    "ForceSensorEvent",
    "SensorEvent",
    "SensorSource",
    # Type classes
    "O7Angle",
    "O7Torque",
    "O7Speed",
    "O7Acceleration",
    "O7Temperature",
    "O7Fault",
    "FaultCode",
    "Version",
    "DeviceInfo",
]
