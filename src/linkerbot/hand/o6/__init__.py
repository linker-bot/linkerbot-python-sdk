"""O6 robotic hand control package.

This package provides the O6 interface for controlling the O6 robotic hand
via CAN bus communication.
"""

from linkerbot.hand.o6.angle import AngleData, O6Angle
from linkerbot.hand.o6.events import (
    AccelerationEvent,
    AngleEvent,
    FaultEvent,
    ForceSensorEvent,
    O6Snapshot,
    SensorEvent,
    SensorSource,
    SpeedEvent,
    TemperatureEvent,
    TorqueEvent,
)
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
    "O6",
    # Managers
    "ForceSensorManager",
    "SingleForceSensorManager",
    "TemperatureManager",
    "FaultManager",
    "StallManager",
    "VersionManager",
    "AccelerationManager",
    "SpeedManager",
    "TorqueManager",
    "FactoryResetManager",
    # Data containers
    "AngleData",
    "TorqueData",
    "SpeedData",
    "AccelerationData",
    "ForceSensorData",
    "AllFingersData",
    "TemperatureData",
    "FaultData",
    "O6Snapshot",
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
    "O6Angle",
    "O6Torque",
    "O6Speed",
    "O6Acceleration",
    "O6Temperature",
    "O6Fault",
    "O6StallTime",
    "O6StallThreshold",
    "O6StallTorque",
    "FaultCode",
    "Version",
    "DeviceInfo",
]
