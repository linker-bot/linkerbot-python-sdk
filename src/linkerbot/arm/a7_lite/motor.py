import struct
import time
from enum import Enum

import can

from linkerbot.arm.common import ControlMode
from linkerbot.arm.common.model import (
    AccelerationState,
    AngleState,
    TemperatureState,
    TorqueState,
    VelocityState,
)
from linkerbot.comm import CANMessageDispatcher
from linkerbot.relay import DataRelay

_MASTER_ID = 0xFD


class CommType(int, Enum):
    Type2 = 0x02
    Type3 = 0x03
    Type4 = 0x04
    Type6 = 0x06
    Type17 = 0x11
    Type18 = 0x12
    Type21 = 0x15
    Type22 = 0x16
    Type24 = 0x18


class A7liteMotor:
    _CONTROL_MODE_MAP = {
        ControlMode.PP: 0x01,
    }

    def __init__(self, id: int, dispatcher: CANMessageDispatcher) -> None:
        self._id = id
        self._dispatcher = dispatcher
        self._angle: AngleState
        self._control_angle: AngleState
        self._velocity: VelocityState
        self._control_velocity: VelocityState
        self._control_acceleration: AccelerationState
        self._torque: TorqueState
        self._temperature: TemperatureState
        self._loc_kp: float
        self._speed_kp: float
        self._speed_ki: float
        self._speed_filt_gain: float
        self._read_relay: DataRelay[bytes] = DataRelay()

        self._dispatcher.subscribe(self._on_message)

    @property
    def angle(self) -> AngleState:
        return self._angle

    @property
    def control_angle(self) -> AngleState:
        return self._control_angle

    @property
    def velocity(self) -> VelocityState:
        return self._velocity

    @property
    def control_velocity(self) -> VelocityState:
        return self._control_velocity

    @property
    def control_acceleration(self) -> AccelerationState:
        return self._control_acceleration

    @property
    def torque(self) -> TorqueState:
        return self._torque

    @property
    def temperature(self) -> TemperatureState:
        return self._temperature

    @property
    def loc_kp(self) -> float:
        return self._loc_kp

    @property
    def speed_kp(self) -> float:
        return self._speed_kp

    @property
    def speed_ki(self) -> float:
        return self._speed_ki

    @property
    def speed_filt_gain(self) -> float:
        return self._speed_filt_gain

    def _generate_arbitration_id(self, comm_type: CommType) -> int:
        motor_id_part = self._id & 0xFF
        master_id_part = _MASTER_ID << 8
        comm_type_part = (comm_type & 0x1F) << 24
        return motor_id_part | master_id_part | comm_type_part

    def _send(self, comm_type: CommType, data: bytes) -> None:
        msg = can.Message(
            arbitration_id=self._generate_arbitration_id(comm_type),
            data=data,
            is_extended_id=True,
        )
        self._dispatcher.send(msg)

    def set_control_mode(self, mode: ControlMode) -> None:
        self._write_register_u32(0x7005, self._CONTROL_MODE_MAP[mode])

    def enable(self) -> None:
        self._send(CommType.Type3, bytes(8))

    def disable(self) -> None:
        self._send(CommType.Type4, bytes(8))

    def calibrate_zero(self) -> None:
        self._send(CommType.Type6, b"\x01" + bytes(7))
        self._save_params()
        time.sleep(0.001)

    def reset_error(self) -> None:
        self._send(CommType.Type4, b"\x01" + bytes(7))

    def set_angle(self, angle: float) -> None:
        self._control_angle = AngleState(angle=angle, timestamp=time.time())
        self._write_register_float(0x7016, angle)

    def set_velocity(self, velocity: float) -> None:
        self._control_velocity = VelocityState(velocity=velocity, timestamp=time.time())
        self._write_register_float(0x7024, velocity)

    def set_acceleration(self, acceleration: float) -> None:
        self._control_acceleration = AccelerationState(
            acceleration=acceleration, timestamp=time.time()
        )
        self._write_register_float(0x7025, acceleration)

    def set_position_kp(self, kp: float) -> None:
        self._loc_kp = kp
        self._write_register_float(0x701E, kp)

    def set_velocity_kp(self, kp: float) -> None:
        self._speed_kp = kp
        self._write_register_float(0x701F, kp)

    def set_velicity_ki(self, ki: float) -> None:
        self._speed_ki = ki
        self._write_register_float(0x7020, ki)

    def set_velocity_filt_gain(self, gain: float) -> None:
        self._speed_filt_gain = gain
        self._write_register_float(0x7021, gain)

    def has_reporting_data(self) -> bool:
        return all(
            hasattr(self, attr)
            for attr in ("_angle", "_velocity", "_torque", "_temperature")
        )

    def start_reporting(self) -> None:
        self._send(CommType.Type24, b"\x01\x02\x03\x04\x05\x06\x01\x00")

    def _write_register(self, register: int, value: bytes) -> None:
        self._send(CommType.Type18, struct.pack("<HH", register, 0) + value)

    def _write_register_float(self, register: int, value: float) -> None:
        self._write_register(register, struct.pack("<f", value))

    def _write_register_u32(self, register: int, value: int) -> None:
        self._write_register(register, struct.pack("<I", value))

    def _read_register(self, register: int, timeout_s: float = 1.0) -> bytes:
        self._send(CommType.Type17, struct.pack("<HH", register, 0) + bytes(4))
        return self._read_relay.wait(timeout_s)

    def _read_register_float(self, register: int, timeout_s: float = 1.0) -> float:
        data = self._read_register(register, timeout_s)
        return struct.unpack("<f", data)[0]

    def _save_params(self) -> None:
        self._send(CommType.Type22, b"\x01\x02\x03\x04\x05\x06\x07\x08")

    def check_alive(self, timeout_s: float = 0.02) -> bool:
        """Check if the motor responds on the CAN bus."""
        try:
            self._read_register(0x7016, timeout_s)
            return True
        except TimeoutError:
            return False

    def read_initial_state(self, timeout_s: float = 1.0) -> None:
        now = time.time()
        self._control_angle = AngleState(
            angle=self._read_register_float(0x7016, timeout_s), timestamp=now
        )
        self._control_velocity = VelocityState(
            velocity=self._read_register_float(0x7024, timeout_s), timestamp=now
        )
        self._control_acceleration = AccelerationState(
            acceleration=self._read_register_float(0x7025, timeout_s), timestamp=now
        )
        self._loc_kp = self._read_register_float(0x701E, timeout_s)
        self._speed_kp = self._read_register_float(0x701F, timeout_s)
        self._speed_ki = self._read_register_float(0x7020, timeout_s)
        self._speed_filt_gain = self._read_register_float(0x7021, timeout_s)

    def _on_message(self, msg: can.Message) -> None:
        arb_id = msg.arbitration_id
        comm_type = (arb_id >> 24) & 0x1F

        motor_id = (arb_id >> 8) & 0xFF
        if motor_id != self._id:
            return

        if comm_type == CommType.Type17:
            status = (arb_id >> 16) & 0xFF
            if status == 0x00:
                self._read_relay.push(bytes(msg.data[4:8]))
            return

        if comm_type not in (CommType.Type2, CommType.Type24):
            return

        now = time.time()
        raw_angle, raw_velocity, raw_torque, raw_temp = struct.unpack(">HHHH", msg.data)

        self._angle = AngleState(
            angle=raw_angle / 65535.0 * 25.14 - 12.57, timestamp=now
        )
        self._velocity = VelocityState(
            velocity=raw_velocity / 65535.0 * 66.0 - 33.0, timestamp=now
        )
        self._torque = TorqueState(
            torque=raw_torque / 65535.0 * 28.0 - 14.0, timestamp=now
        )
        self._temperature = TemperatureState(temperature=raw_temp / 10.0, timestamp=now)
