"""Unit tests for A7lite.emergency_stop per-joint mode dispatch (no hardware)."""

from __future__ import annotations

import struct
import time
from collections.abc import Callable

import can
import pytest

from linkerbot.arm.a7_lite.a7_lite import A7lite
from linkerbot.arm.a7_lite.consts import (
    MIT_HOLD_KD,
    MIT_HOLD_KP,
    MIT_KP_MAX,
    MIT_P_MAX,
    MIT_P_MIN,
    MIT_T_MAX,
    MIT_T_MIN,
)
from linkerbot.arm.a7_lite.motor import A7liteMotor, CommType, float_to_uint
from linkerbot.arm.common import ControlMode
from linkerbot.arm.common.model import (
    AngleState,
    TemperatureState,
    TorqueState,
    VelocityState,
)


class _FakeDispatcher:
    def __init__(self) -> None:
        self.sent: list[can.Message] = []
        self._subscribers: list[Callable[[can.Message], None]] = []

    def subscribe(self, callback: Callable[[can.Message], None]) -> None:
        self._subscribers.append(callback)

    def send(self, msg: can.Message) -> None:
        self.sent.append(msg)


def _make_arm(modes: list[ControlMode]) -> tuple[A7lite, _FakeDispatcher, list[A7liteMotor]]:
    dispatcher = _FakeDispatcher()
    motors = [
        A7liteMotor(id=61 + i, dispatcher=dispatcher)  # type: ignore[arg-type]
        for i in range(7)
    ]
    now = time.time()
    for i, motor in enumerate(motors):
        motor._angle = AngleState(angle=0.1 * i, timestamp=now)
        motor._velocity = VelocityState(velocity=0.0, timestamp=now)
        motor._torque = TorqueState(torque=0.0, timestamp=now)
        motor._temperature = TemperatureState(temperature=25.0, timestamp=now)
        motor._control_velocity = VelocityState(velocity=1.5, timestamp=now)
        motor._limit_spd = 2.5

    arm = A7lite.__new__(A7lite)
    arm._motors = motors
    arm._control_modes = list(modes)
    return arm, dispatcher, motors


def _register_writes(sent: list[can.Message]) -> list[tuple[int, int, bytes]]:
    """Return (motor_id, register, value_bytes) for Type18 writes."""
    out: list[tuple[int, int, bytes]] = []
    for msg in sent:
        if ((msg.arbitration_id >> 24) & 0x1F) != CommType.Type18:
            continue
        motor_id = msg.arbitration_id & 0xFF
        index = struct.unpack_from("<H", bytes(msg.data), 0)[0]
        out.append((motor_id, index, bytes(msg.data[4:8])))
    return out


def _mit_frames(sent: list[can.Message]) -> list[can.Message]:
    return [m for m in sent if ((m.arbitration_id >> 24) & 0x1F) == CommType.Type1]


class TestEmergencyStopPerMode:
    def test_all_pp_zeros_vel_max_7024(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(time, "sleep", lambda _s: None)
        arm, dispatcher, motors = _make_arm([ControlMode.PP] * 7)

        arm.emergency_stop()

        writes = _register_writes(dispatcher.sent)
        zero_writes = [
            (mid, reg, struct.unpack("<f", val)[0])
            for mid, reg, val in writes
            if reg == 0x7024
        ]
        # 7 zeros then 7 restores
        assert [v for _, _, v in zero_writes[:7]] == pytest.approx([0.0] * 7)
        assert [v for _, _, v in zero_writes[7:14]] == pytest.approx([1.5] * 7)
        assert _mit_frames(dispatcher.sent) == []
        assert not any(reg == 0x7017 for _, reg, _ in writes)

    def test_all_csp_zeros_limit_spd_7017(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(time, "sleep", lambda _s: None)
        arm, dispatcher, _motors = _make_arm([ControlMode.CSP] * 7)

        arm.emergency_stop()

        writes = _register_writes(dispatcher.sent)
        limit_writes = [
            (mid, reg, struct.unpack("<f", val)[0])
            for mid, reg, val in writes
            if reg == 0x7017
        ]
        assert [v for _, _, v in limit_writes[:7]] == pytest.approx([0.0] * 7)
        assert [v for _, _, v in limit_writes[7:14]] == pytest.approx([2.5] * 7)
        assert not any(reg == 0x7024 for _, reg, _ in writes)
        assert _mit_frames(dispatcher.sent) == []

    def test_all_mit_sends_type1_hold(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(time, "sleep", lambda _s: None)
        arm, dispatcher, motors = _make_arm([ControlMode.MIT] * 7)
        for motor in motors:
            motor.set_mit(0.5, 1.0, 30.0, 2.0, torque=1.0)
        dispatcher.sent.clear()

        arm.emergency_stop()

        mit = _mit_frames(dispatcher.sent)
        assert len(mit) == 7
        for i, msg in enumerate(mit):
            assert (msg.arbitration_id & 0xFF) == 61 + i
            torque_u = (msg.arbitration_id >> 8) & 0xFFFF
            assert torque_u == float_to_uint(0.0, MIT_T_MIN, MIT_T_MAX, 16)
            _p_u, v_u, kp_u, kd_u = struct.unpack(">HHHH", bytes(msg.data))
            assert v_u == float_to_uint(0.0, -33.0, 33.0, 16)
            assert kp_u == float_to_uint(30.0, 0.0, MIT_KP_MAX, 16)
            assert kd_u == float_to_uint(2.0, 0.0, 5.0, 16)
            # hold at measured angle (0.1 * i)
            assert _p_u == float_to_uint(0.1 * i, MIT_P_MIN, MIT_P_MAX, 16)

        writes = _register_writes(dispatcher.sent)
        assert not any(reg in (0x7024, 0x7017) for _, reg, _ in writes)

    def test_mixed_mit_pp_dispatches_per_joint(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """First three MIT, last four PP — the documented mixed-mode case."""
        monkeypatch.setattr(time, "sleep", lambda _s: None)
        modes = [ControlMode.MIT] * 3 + [ControlMode.PP] * 4
        arm, dispatcher, motors = _make_arm(modes)
        for motor in motors[:3]:
            motor.set_mit(0.2, 0.0, 25.0, 1.5, torque=0.0)
        dispatcher.sent.clear()

        arm.emergency_stop()

        mit = _mit_frames(dispatcher.sent)
        assert len(mit) == 3
        assert {(m.arbitration_id & 0xFF) for m in mit} == {61, 62, 63}

        writes = _register_writes(dispatcher.sent)
        zero_pp = [
            mid
            for mid, reg, val in writes
            if reg == 0x7024 and abs(struct.unpack("<f", val)[0]) < 1e-9
        ]
        assert zero_pp == [64, 65, 66, 67]
        assert not any(reg == 0x7017 for _, reg, _ in writes)

    def test_mixed_csp_pp_uses_correct_registers(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(time, "sleep", lambda _s: None)
        modes = [ControlMode.CSP] * 2 + [ControlMode.PP] * 5
        arm, dispatcher, _motors = _make_arm(modes)

        arm.emergency_stop()

        writes = _register_writes(dispatcher.sent)
        zero_csp = [
            mid
            for mid, reg, val in writes
            if reg == 0x7017 and abs(struct.unpack("<f", val)[0]) < 1e-9
        ]
        zero_pp = [
            mid
            for mid, reg, val in writes
            if reg == 0x7024 and abs(struct.unpack("<f", val)[0]) < 1e-9
        ]
        assert zero_csp == [61, 62]
        assert zero_pp == [63, 64, 65, 66, 67]
        assert _mit_frames(dispatcher.sent) == []

    def test_mit_hold_uses_fallback_gains_when_never_commanded(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(time, "sleep", lambda _s: None)
        arm, dispatcher, motors = _make_arm([ControlMode.MIT] * 7)
        assert motors[0].mit_kp is None

        arm.emergency_stop()

        msg = _mit_frames(dispatcher.sent)[0]
        _p_u, _v_u, kp_u, kd_u = struct.unpack(">HHHH", bytes(msg.data))
        assert kp_u == float_to_uint(MIT_HOLD_KP, 0.0, MIT_KP_MAX, 16)
        assert kd_u == float_to_uint(MIT_HOLD_KD, 0.0, 5.0, 16)

    def test_unset_modes_default_to_pp(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(time, "sleep", lambda _s: None)
        arm, dispatcher, _motors = _make_arm([ControlMode.PP] * 7)
        arm._control_modes = None

        arm.emergency_stop()

        writes = _register_writes(dispatcher.sent)
        assert any(reg == 0x7024 for _, reg, _ in writes)
        assert not any(reg == 0x7017 for _, reg, _ in writes)
        assert _mit_frames(dispatcher.sent) == []
