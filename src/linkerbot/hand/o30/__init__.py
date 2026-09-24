"""Public O30 SDK API."""

from linkerbot.hand.hand_protocol_v1 import (
    HandProtocolDeviceError,
    HandProtocolError,
    HandProtocolV1,
)

from .acceleration import AccelerationManager, O30AccelerationData
from .angle import AngleManager, O30AngleData
from .current import CurrentManager, O30CurrentData
from .diagnostics import DiagnosticsManager, O30CommunicationErrors
from .events import (
    AccelerationEvent,
    AngleEvent,
    CurrentEvent,
    FaultEvent,
    MotionTimeEvent,
    O30Snapshot,
    SensorEvent,
    SensorSource,
    SpeedEvent,
    TemperatureEvent,
    TorqueEvent,
    VoltageEvent,
)
from .fault import FaultManager, O30FaultData
from .joints import (
    O30_DEFAULT_RAW_VALUES,
    O30_JOINT_COUNT,
    O30_JOINT_SPECS,
    JointSpec,
    O30Angle,
)
from .motion_time import MotionTimeManager, O30MotionTimeData
from .o30 import O30
from .protocol import O30Object
from .sensor import O30SensorInfo, SensorManager
from .speed import O30SpeedData, SpeedManager
from .temperature import O30TemperatureData, TemperatureManager
from .torque import O30TorqueData, TorqueManager
from .version import O30DeviceInfo, VersionManager
from .voltage import O30VoltageData, VoltageManager

__all__ = [
    "AccelerationEvent",
    "AccelerationManager",
    "AngleEvent",
    "AngleManager",
    "CurrentEvent",
    "CurrentManager",
    "DiagnosticsManager",
    "FaultEvent",
    "FaultManager",
    "HandProtocolDeviceError",
    "HandProtocolError",
    "HandProtocolV1",
    "MotionTimeEvent",
    "MotionTimeManager",
    "O30_DEFAULT_RAW_VALUES",
    "O30_JOINT_COUNT",
    "O30_JOINT_SPECS",
    "O30",
    "O30AccelerationData",
    "O30Angle",
    "O30AngleData",
    "O30CommunicationErrors",
    "O30CurrentData",
    "O30DeviceInfo",
    "O30FaultData",
    "O30MotionTimeData",
    "O30Object",
    "O30SensorInfo",
    "O30Snapshot",
    "O30SpeedData",
    "O30TemperatureData",
    "O30TorqueData",
    "O30VoltageData",
    "JointSpec",
    "SensorEvent",
    "SensorManager",
    "SensorSource",
    "SpeedEvent",
    "SpeedManager",
    "TemperatureEvent",
    "TemperatureManager",
    "TorqueEvent",
    "TorqueManager",
    "VersionManager",
    "VoltageEvent",
    "VoltageManager",
]
