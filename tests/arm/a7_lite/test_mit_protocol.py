"""Unit tests for A7 Lite RS00 MIT / 运控 packing (no hardware)."""

from __future__ import annotations

import struct
import time
from collections.abc import Callable

import can
import pytest

from linkerbot.arm.a7_lite.a7_lite import A7lite
from linkerbot.arm.a7_lite.consts import (
    MIT_KD_MAX,
    MIT_KP_MAX,
    MIT_P_MAX,
    MIT_P_MIN,
    MIT_T_MAX,
    MIT_T_MIN,
    MIT_V_MAX,
    MIT_V_MIN,
)
from linkerbot.arm.a7_lite.motor import A7liteMotor, CommType, float_to_uint
from linkerbot.arm.common import ControlMode
from linkerbot.arm.common.model import (
    AccelerationState,
    AngleState,
    VelocityState,
)
from linkerbot.exceptions import ValidationError
from linkerbot.motion_timer import MotionTimer


class _FakeDispatcher:
    def __init__(self) -> None:
        self.sent: list[can.Message] = []
        self._subscribers: list[Callable[[can.Message], None]] = []

    def subscribe(self, callback: Callable[[can.Message], None]) -> None:
        self._subscribers.append(callback)

    def send(self, msg: can.Message) -> None:
        self.sent.append(msg)


class TestFloatToUint:
    def test_endpoints(self) -> None:
        assert float_to_uint(MIT_P_MIN, MIT_P_MIN, MIT_P_MAX, 16) == 0
        assert float_to_uint(MIT_P_MAX, MIT_P_MIN, MIT_P_MAX, 16) == 65535

    def test_midpoint_position(self) -> None:
        mid = float_to_uint(0.0, MIT_P_MIN, MIT_P_MAX, 16)
        assert mid == 32767 or mid == 32768  # float rounding

    def test_clamps(self) -> None:
        assert float_to_uint(99.0, MIT_T_MIN, MIT_T_MAX, 16) == 65535
        assert float_to_uint(-99.0, MIT_T_MIN, MIT_T_MAX, 16) == 0


class TestSetMitFrame:
    def test_arbitration_id_and_payload(self) -> None:
        dispatcher = _FakeDispatcher()
        motor = A7liteMotor(id=51, dispatcher=dispatcher)  # type: ignore[arg-type]

        position = 0.0
        velocity = 0.0
        kp = 20.0
        kd = 1.0
        torque = 0.0
        motor.set_mit(position, velocity, kp, kd, torque)

        assert len(dispatcher.sent) == 1
        msg = dispatcher.sent[0]
        assert msg.is_extended_id is True

        comm_type = (msg.arbitration_id >> 24) & 0x1F
        torque_u = (msg.arbitration_id >> 8) & 0xFFFF
        motor_id = msg.arbitration_id & 0xFF
        assert comm_type == CommType.Type1
        assert motor_id == 51
        assert torque_u == float_to_uint(torque, MIT_T_MIN, MIT_T_MAX, 16)

        p_u, v_u, kp_u, kd_u = struct.unpack(">HHHH", bytes(msg.data))
        assert p_u == float_to_uint(position, MIT_P_MIN, MIT_P_MAX, 16)
        assert v_u == float_to_uint(velocity, MIT_V_MIN, MIT_V_MAX, 16)
        assert kp_u == float_to_uint(kp, 0.0, MIT_KP_MAX, 16)
        assert kd_u == float_to_uint(kd, 0.0, MIT_KD_MAX, 16)

    def test_nonzero_torque_in_can_id(self) -> None:
        dispatcher = _FakeDispatcher()
        motor = A7liteMotor(id=61, dispatcher=dispatcher)  # type: ignore[arg-type]
        motor.set_mit(1.0, -2.0, 10.0, 0.5, torque=3.5)

        msg = dispatcher.sent[-1]
        torque_u = (msg.arbitration_id >> 8) & 0xFFFF
        assert torque_u == float_to_uint(3.5, MIT_T_MIN, MIT_T_MAX, 16)
        assert (msg.arbitration_id & 0xFF) == 61


class TestControlModeMap:
    def test_mit_pp_and_csp_run_mode_values(self) -> None:
        assert A7liteMotor._CONTROL_MODE_MAP[ControlMode.PP] == 0x01
        assert A7liteMotor._CONTROL_MODE_MAP[ControlMode.MIT] == 0x00
        assert A7liteMotor._CONTROL_MODE_MAP[ControlMode.CSP] == 0x05

    def test_set_control_mode_writes_run_mode_register(self) -> None:
        dispatcher = _FakeDispatcher()
        motor = A7liteMotor(id=51, dispatcher=dispatcher)  # type: ignore[arg-type]
        motor.set_control_mode(ControlMode.MIT)

        msg = dispatcher.sent[-1]
        assert ((msg.arbitration_id >> 24) & 0x1F) == CommType.Type18
        index, _pad = struct.unpack_from("<HH", bytes(msg.data), 0)
        assert index == 0x7005
        (value,) = struct.unpack_from("<I", bytes(msg.data), 4)
        assert value == 0

    def test_set_control_mode_csp(self) -> None:
        dispatcher = _FakeDispatcher()
        motor = A7liteMotor(id=51, dispatcher=dispatcher)  # type: ignore[arg-type]
        motor.set_control_mode(ControlMode.CSP)
        msg = dispatcher.sent[-1]
        index = struct.unpack_from("<H", bytes(msg.data), 0)[0]
        value = struct.unpack_from("<I", bytes(msg.data), 4)[0]
        assert index == 0x7005
        assert value == 0x05


class TestCspLimitSpd:
    def test_writes_register_7017(self) -> None:
        dispatcher = _FakeDispatcher()
        motor = A7liteMotor(id=61, dispatcher=dispatcher)  # type: ignore[arg-type]
        motor.set_limit_spd(2.5)
        assert motor.limit_spd == 2.5
        msg = dispatcher.sent[-1]
        assert ((msg.arbitration_id >> 24) & 0x1F) == CommType.Type18
        index = struct.unpack_from("<H", bytes(msg.data), 0)[0]
        (value,) = struct.unpack_from("<f", bytes(msg.data), 4)
        assert index == 0x7017
        assert abs(value - 2.5) < 1e-6


class TestMitVelocityCacheIsolation:
    """MIT v_des must not overwrite the PP vel_max (0x7024) cache."""

    def test_set_mit_keeps_pp_control_velocity(self) -> None:
        dispatcher = _FakeDispatcher()
        motor = A7liteMotor(id=51, dispatcher=dispatcher)  # type: ignore[arg-type]
        now = time.time()
        motor._control_velocity = VelocityState(velocity=0.5, timestamp=now)
        assert motor.mit_velocity is None

        motor.set_mit(0.1, 0.0, 20.0, 1.0, torque=0.0)

        assert motor.control_velocity.velocity == pytest.approx(0.5)
        assert motor.mit_velocity == pytest.approx(0.0)
        assert motor.mit_kp == pytest.approx(20.0)
        assert motor.mit_kd == pytest.approx(1.0)
        # set_mit must not write PP register 0x7024
        assert not any(
            ((m.arbitration_id >> 24) & 0x1F) == CommType.Type18
            and struct.unpack_from("<H", bytes(m.data), 0)[0] == 0x7024
            for m in dispatcher.sent
        )

    def test_move_duration_after_mit_uses_pp_speed(self) -> None:
        """Regression: MIT→PP must not make move_j duration collapse to ~0."""
        dispatcher = _FakeDispatcher()
        motors = [
            A7liteMotor(id=61 + i, dispatcher=dispatcher)  # type: ignore[arg-type]
            for i in range(7)
        ]
        now = time.time()
        current = [0.0] * 7
        target = [0.0] * 7
        target[0] = 1.025  # ~2.05 s at v=1.0, a=1.0
        for motor in motors:
            motor._control_velocity = VelocityState(velocity=1.0, timestamp=now)
            motor._control_acceleration = AccelerationState(
                acceleration=1.0, timestamp=now
            )
            motor._angle = AngleState(angle=0.0, timestamp=now)
            motor.set_mit(0.0, 0.0, 20.0, 1.0)  # default MIT v_des = 0

        arm = A7lite.__new__(A7lite)
        arm._motors = motors
        arm._control_modes = [ControlMode.PP] * 7
        arm._motion_timer = MotionTimer()

        duration = arm._move_duration(
            current,
            target,
            arm.get_control_velocities(),
            arm.get_control_acceleration(),
        )
        assert duration == pytest.approx(2.025, abs=1e-6)

        arm._motion_timer.start(duration)
        assert arm.is_moving() is True
        try:
            assert arm._motion_timer.wait_done(timeout=0.05) is False
        finally:
            arm._motion_timer.cancel()


class TestStreamJointTargetsBatchValidate:
    """Regression: validate all MIT joints before any send."""

    def _make_arm(self, modes: list[ControlMode]) -> tuple[A7lite, _FakeDispatcher]:
        dispatcher = _FakeDispatcher()
        motors = [
            A7liteMotor(id=61 + i, dispatcher=dispatcher)  # type: ignore[arg-type]
            for i in range(7)
        ]
        arm = A7lite.__new__(A7lite)
        arm._motors = motors
        arm._control_modes = list(modes)
        return arm, dispatcher

    def test_invalid_later_mit_sends_nothing_mixed_pp(self) -> None:
        """PP joints must not get loc_ref if a later MIT joint fails validation."""
        modes = [ControlMode.PP] * 3 + [ControlMode.MIT] * 4
        arm, dispatcher = self._make_arm(modes)

        kps = [20.0] * 7
        kps[6] = MIT_KP_MAX + 1.0

        with pytest.raises(ValidationError, match=r"Joint 6 MIT kp"):
            arm.stream_joint_targets(
                [0.0] * 7,
                kps=kps,
                kds=[1.0] * 7,
                check_limits=False,
            )

        assert dispatcher.sent == []

    def test_invalid_later_mit_sends_nothing_all_mit(self) -> None:
        arm, dispatcher = self._make_arm([ControlMode.MIT] * 7)

        kps = [20.0] * 7
        kps[6] = MIT_KP_MAX + 1.0

        with pytest.raises(ValidationError, match=r"Joint 6 MIT kp"):
            arm.stream_joint_targets(
                [0.0] * 7,
                kps=kps,
                kds=[1.0] * 7,
                check_limits=False,
            )

        assert dispatcher.sent == []

    def test_valid_mixed_still_sends(self) -> None:
        """Sanity: batch path still dispatches when all MIT params are valid."""
        modes = [ControlMode.MIT] * 3 + [ControlMode.PP] * 4
        arm, dispatcher = self._make_arm(modes)

        arm.stream_joint_targets(
            [0.0] * 7,
            kps=[20.0] * 7,
            kds=[1.0] * 7,
            check_limits=False,
        )

        mit = [
            m
            for m in dispatcher.sent
            if ((m.arbitration_id >> 24) & 0x1F) == CommType.Type1
        ]
        loc_ref = [
            m
            for m in dispatcher.sent
            if ((m.arbitration_id >> 24) & 0x1F) == CommType.Type18
            and struct.unpack_from("<H", bytes(m.data), 0)[0] == 0x7016
        ]
        assert len(mit) == 3
        assert len(loc_ref) == 4
