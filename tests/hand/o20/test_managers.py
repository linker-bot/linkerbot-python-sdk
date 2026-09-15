from __future__ import annotations

import pytest

from linkerbot.exceptions import ValidationError
from linkerbot.hand.o20 import protocol
from linkerbot.hand.o20.angle import AngleManager
from linkerbot.hand.o20.client import O20Client
from linkerbot.hand.o20.current import CurrentManager
from linkerbot.hand.o20.fault import FaultManager
from linkerbot.hand.o20.joints import O20_JOINT_SPECS
from linkerbot.hand.o20.speed import SpeedManager
from linkerbot.hand.o20.temperature import TemperatureManager
from linkerbot.hand.o20.torque import TorqueManager
from tests.hand.o20.fakes import FakeDispatcher

pytestmark = [pytest.mark.o20, pytest.mark.canfd]


def test_angle_set_raw_angles_writes_target_pos_with_little_endian_payload() -> None:
    dispatcher = FakeDispatcher()
    client = O20Client(dispatcher, device_id=0x01)
    manager = AngleManager(client)

    manager.set_raw_angles([1] * protocol.O20_JOINT_COUNT)

    sent = dispatcher.sent[0]
    assert sent.arbitration_id == 0x0020D000
    assert sent.data[:32] == b"\x01\x00" * 16
    assert sent.data[32:] == b"\x00\x00"
    assert sent.dlc == protocol.O20_VECTOR_DLC


def test_angle_get_blocking_decodes_first_sixteen_motor_slots_only() -> None:
    response = b"".join(
        value.to_bytes(2, "little", signed=True) for value in [*range(1, 17), 12345]
    )
    dispatcher = FakeDispatcher(responses={protocol.O20_REG_CURRENT_POS: response})
    manager = AngleManager(O20Client(dispatcher, device_id=0x01))

    data = manager.get_blocking(timeout_ms=100)

    # Sensor readback stores percentages internally; compare via to_raw() to
    # keep the "raw N in → raw N out" assertion without recomputing per-joint
    # percentage values.
    snapshot = manager.get_snapshot()
    assert data.angles.to_raw() == list(range(1, 17))
    assert snapshot is not None
    assert snapshot.angles.to_raw() == list(range(1, 17))


def test_angle_set_angles_uses_per_joint_minimum_and_maximum() -> None:
    dispatcher = FakeDispatcher()
    client = O20Client(dispatcher, device_id=0x01)
    manager = AngleManager(client)

    manager.set_angles([0.0] * protocol.O20_JOINT_COUNT)

    expected = [spec.minimum for spec in O20_JOINT_SPECS]
    payload = dispatcher.sent[0].data
    decoded = [
        int.from_bytes(payload[index * 2 : index * 2 + 2], "little", signed=True)
        for index in range(16)
    ]
    assert decoded == expected


def test_speed_command_uses_target_vel_register_and_validates_range() -> None:
    dispatcher = FakeDispatcher()
    manager = SpeedManager(O20Client(dispatcher, device_id=0x01))

    manager.set_all(50)

    assert dispatcher.sent[0].arbitration_id == 0x0020F000
    assert dispatcher.sent[0].data[:32] == b"\x32\x00" * 16
    with pytest.raises(ValidationError):
        manager.set_all(101)


def test_torque_command_uses_target_torque_register_and_caches_targets() -> None:
    dispatcher = FakeDispatcher()
    manager = TorqueManager(O20Client(dispatcher, device_id=0x01))

    manager.set_torques([400] * protocol.O20_JOINT_COUNT)

    assert dispatcher.sent[0].arbitration_id == 0x00211000
    assert dispatcher.sent[0].data[:32] == b"\x90\x01" * 16
    snapshot = manager.get_snapshot()
    assert snapshot is not None
    assert snapshot.torques == (400,) * 16


def test_current_get_blocking_decodes_motor_currents() -> None:
    response = b"".join(
        value.to_bytes(2, "little", signed=True) for value in [*range(0, 16), 999]
    )
    dispatcher = FakeDispatcher(responses={protocol.O20_REG_MOTOR_CURRENT: response})
    manager = CurrentManager(O20Client(dispatcher, device_id=0x01))

    data = manager.get_blocking(timeout_ms=100)

    assert data.currents == tuple(range(16))


def test_temperature_get_blocking_decodes_per_motor_bytes() -> None:
    response = bytes(range(20))
    dispatcher = FakeDispatcher(responses={protocol.O20_REG_TEMP_DATA: response})
    manager = TemperatureManager(O20Client(dispatcher, device_id=0x01))

    data = manager.get_blocking(timeout_ms=100)

    assert data.temperatures == tuple(range(16))


def test_fault_get_blocking_decodes_per_motor_status() -> None:
    response = bytes([0, 1, 2, 3, 4, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0])
    dispatcher = FakeDispatcher(responses={protocol.O20_REG_ERROR_STATUS: response})
    manager = FaultManager(O20Client(dispatcher, device_id=0x01))

    data = manager.get_blocking(timeout_ms=100)

    assert data.faults[:5] == (0, 1, 2, 3, 4)
    assert data.has_fault(0) is False
    assert data.has_fault(1) is True
    assert data.fault_message(2) == "over current"


def test_fault_clear_writes_zero_byte_vector_to_error_status_register() -> None:
    dispatcher = FakeDispatcher()
    manager = FaultManager(O20Client(dispatcher, device_id=0x01))

    manager.clear()

    sent = dispatcher.sent[0]
    assert sent.arbitration_id == 0x00205000
    assert sent.data == bytes(17)
    assert sent.dlc == protocol.O20_U8_VECTOR_DLC
