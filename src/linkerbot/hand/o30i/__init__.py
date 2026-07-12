"""Public O30i SDK API."""

from linkerbot.hand.hand_protocol_v1 import (
    HandProtocolDeviceError,
    HandProtocolError,
    HandProtocolV1,
)

from .acceleration import AccelerationManager, O30iAccelerationData
from .angle import AngleManager, O30iAngleData
from .current import CurrentManager, O30iCurrentData
from .diagnostics import DiagnosticsManager, O30iCommunicationErrors
from .events import (
    AccelerationEvent,
    AngleEvent,
    CurrentEvent,
    FaultEvent,
    MotionTimeEvent,
    O30iSnapshot,
    SensorEvent,
    SensorSource,
    SpeedEvent,
    TemperatureEvent,
    TorqueEvent,
    VoltageEvent,
)
from .fault import FaultManager, O30iFaultData
from .joints import (
    O30I_DEFAULT_RAW_VALUES,
    O30I_JOINT_COUNT,
    O30I_JOINT_SPECS,
    JointSpec,
    O30iAngle,
)
from .motion_time import MotionTimeManager, O30iMotionTimeData
from .o30i import O30i
from .protocol import O30iObject
from .sensor import O30iSensorInfo, SensorManager
from .speed import O30iSpeedData, SpeedManager
from .temperature import O30iTemperatureData, TemperatureManager
from .torque import O30iTorqueData, TorqueManager
from .version import O30iDeviceInfo, VersionManager
from .voltage import O30iVoltageData, VoltageManager

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
    "O30I_DEFAULT_RAW_VALUES",
    "O30I_JOINT_COUNT",
    "O30I_JOINT_SPECS",
    "O30i",
    "O30iAccelerationData",
    "O30iAngle",
    "O30iAngleData",
    "O30iCommunicationErrors",
    "O30iCurrentData",
    "O30iDeviceInfo",
    "O30iFaultData",
    "O30iMotionTimeData",
    "O30iObject",
    "O30iSensorInfo",
    "O30iSnapshot",
    "O30iSpeedData",
    "O30iTemperatureData",
    "O30iTorqueData",
    "O30iVoltageData",
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
