from __future__ import annotations

import pytest

from linkerbot.exceptions import ValidationError
from linkerbot.hand.o30i import O30i, protocol
from tests.hand.o30i.fakes import FakeO30iDispatcher

pytestmark = [pytest.mark.o30i, pytest.mark.canfd]

_RUNTIME = bytes(range(protocol.O30I_RUNTIME_SLOT_COUNT))


@pytest.mark.parametrize(
    ("manager_name", "main_index", "field_name"),
    [
        ("speed", protocol.O30I_MI_SPEED, "speeds"),
        ("acceleration", protocol.O30I_MI_ACCELERATION, "accelerations"),
        ("current", protocol.O30I_MI_CURRENT, "currents"),
        ("voltage", protocol.O30I_MI_VOLTAGE, "voltages"),
        ("torque", protocol.O30I_MI_TORQUE, "torques"),
        ("temperature", protocol.O30I_MI_TEMPERATURE, "temperatures"),
        ("motion_time", protocol.O30I_MI_MOTION_TIME, "ticks"),
        ("fault", protocol.O30I_MI_FAULT, "faults"),
    ],
)
def test_runtime_managers_read_full_object_but_return_only_physical_joints(
    manager_name: str,
    main_index: int,
    field_name: str,
) -> None:
    dispatcher = FakeO30iDispatcher({main_index: _RUNTIME})

    with O30i(dispatcher=dispatcher) as hand:
        data = getattr(hand, manager_name).get_blocking()

    assert getattr(data, field_name) == (0, *range(5, 15), *range(16, 25))
    assert dispatcher.sent[0].data == bytes((main_index, 0, 36))


def test_angle_reads_actual_and_target_vectors() -> None:
    actual = bytes(range(36))
    target = bytes(reversed(range(36)))
    dispatcher = FakeO30iDispatcher(
        {
            (protocol.O30I_MI_POSITION, False): actual,
            (protocol.O30I_MI_POSITION, True): target,
        }
    )

    with O30i(dispatcher=dispatcher) as hand:
        actual_data = hand.angle.get_blocking()
        target_angle = hand.angle.get_target_blocking()

    slots = protocol.O30I_JOINT_SLOT_INDICES
    assert actual_data.angles.to_raw() == [actual[index] for index in slots]
    assert target_angle.to_raw() == [target[index] for index in slots]
    assert dispatcher.sent[0].data == bytes.fromhex("01 00 24")
    assert dispatcher.sent[1].data == bytes.fromhex("81 00 24")


def test_full_runtime_writes_touch_only_physical_joint_slots() -> None:
    dispatcher = FakeO30iDispatcher()

    with O30i(dispatcher=dispatcher) as hand:
        hand.angle.set_raw_angles(list(range(20)))
        hand.speed.set_all(10)
        hand.acceleration.set_all(20)
        hand.torque.set_all(30)
        hand.motion_time.set_all_ticks(40)

    assert len(dispatcher.writes) == 15
    assert [write.main_index for write in dispatcher.writes] == [
        item for main_index in (1, 2, 3, 6, 8) for item in (main_index,) * 3
    ]
    assert [write.sub_index for write in dispatcher.writes] == [0, 5, 16] * 5
    assert [len(write.payload) for write in dispatcher.writes] == [1, 10, 9] * 5


def test_position_slice_uses_physical_joint_order() -> None:
    dispatcher = FakeO30iDispatcher()

    with O30i(dispatcher=dispatcher) as hand:
        hand.angle.set_raw_slice(10, [0xAA, 0xBB])
        with pytest.raises(ValidationError, match="20 physical"):
            hand.angle.set_raw_slice(19, [0xAA, 0xBB])

    assert [message.data for message in dispatcher.sent] == [
        bytes.fromhex("01 0E 01 AA"),
        bytes.fromhex("01 10 01 BB"),
    ]


def test_sparse_position_uses_measured_finger_major_wire_ids() -> None:
    dispatcher = FakeO30iDispatcher()

    with O30i(dispatcher=dispatcher) as hand:
        hand.angle.set_sparse({15: 0x80, 16: 0x80})

    assert dispatcher.sent[0].data == bytes.fromhex("30 00 04 04 80 09 80")


def test_motion_time_exact_millisecond_conversion() -> None:
    dispatcher = FakeO30iDispatcher({protocol.O30I_MI_MOTION_TIME: _RUNTIME})

    with O30i(dispatcher=dispatcher) as hand:
        hand.motion_time.set_milliseconds([100] * 20)
        data = hand.motion_time.get_blocking()
        with pytest.raises(ValidationError, match="multiple of 10"):
            hand.motion_time.set_milliseconds([101] * 20)

    assert [write.payload for write in dispatcher.writes] == [
        b"\x0a",
        b"\x0a" * 10,
        b"\x0a" * 9,
    ]
    expected = (0, *range(5, 15), *range(16, 25))
    assert data.milliseconds == tuple(value * 10 for value in expected)


def test_full_i16_read_is_reassembled_and_decoded() -> None:
    values = tuple(range(-18, 18))
    payload = b"".join(value.to_bytes(2, "little", signed=True) for value in values)
    dispatcher = FakeO30iDispatcher({protocol.O30I_MI_POSITION_I16: payload})

    with O30i(dispatcher=dispatcher) as hand:
        result = hand.angle.get_i16_blocking()

    assert result == (values[0], *values[5:15], *values[16:25])
    assert dispatcher.sent[0].data == bytes.fromhex("20 00 48")


def test_fault_data_preserves_raw_bytes_without_inventing_bit_meanings() -> None:
    wire_faults = bytearray(36)
    wire_faults[5] = 3
    dispatcher = FakeO30iDispatcher({protocol.O30I_MI_FAULT: bytes(wire_faults)})

    with O30i(dispatcher=dispatcher) as hand:
        data = hand.fault.get_blocking()

    assert data.has_fault(0) is False
    assert data.has_fault(1) is True
    assert data.faults[1] == 3


@pytest.mark.parametrize("joint_index", [-1, 20, True])
def test_fault_data_rejects_invalid_physical_joint_index(
    joint_index: int,
) -> None:
    dispatcher = FakeO30iDispatcher({protocol.O30I_MI_FAULT: bytes(36)})

    with O30i(dispatcher=dispatcher) as hand:
        data = hand.fault.get_blocking()

    with pytest.raises(ValidationError, match="joint_index"):
        data.has_fault(joint_index)
