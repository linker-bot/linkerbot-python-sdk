from __future__ import annotations

import pytest

from linkerbot.exceptions import ValidationError
from linkerbot.hand.hand_protocol_v1 import HandProtocolError
from linkerbot.hand.o30i import protocol

pytestmark = [pytest.mark.o30i, pytest.mark.canfd]


def test_runtime_read_projects_only_physical_joint_slots() -> None:
    wire = bytes(range(36))

    assert protocol.decode_runtime_vector(wire) == (
        0,
        *range(5, 15),
        *range(16, 25),
    )


def test_runtime_read_rejects_truncated_object() -> None:
    with pytest.raises(HandProtocolError, match="expected 36"):
        protocol.decode_runtime_vector(bytes(35))


def test_complete_control_write_splits_around_unimplemented_slots() -> None:
    writes = protocol.encode_control_vector(list(range(20)))

    assert writes == (
        (0, b"\x00"),
        (5, bytes(range(1, 11))),
        (16, bytes(range(11, 20))),
    )


@pytest.mark.parametrize("values", [list(range(19)), list(range(21))])
def test_complete_control_write_requires_exactly_20_values(values: list[int]) -> None:
    with pytest.raises(ValidationError, match="20 values"):
        protocol.encode_control_vector(values)


def test_control_slices_use_public_joint_indices_and_split_wire_gaps() -> None:
    assert protocol.encode_control_slice(0, [1, 2]) == (
        (0, b"\x01"),
        (5, b"\x02"),
    )
    assert protocol.encode_control_slice(10, [1, 2]) == (
        (14, b"\x01"),
        (16, b"\x02"),
    )
    assert protocol.encode_control_slice(18, [1, 2]) == ((23, b"\x01\x02"),)
    with pytest.raises(ValidationError, match="20 physical"):
        protocol.encode_control_slice(19, [1, 2])
    with pytest.raises(ValidationError, match="must not be empty"):
        protocol.encode_control_slice(0, [])


def test_sparse_positions_translate_physical_joints_to_finger_major_ids() -> None:
    # Public joints 15/16 are thumb/index tips. Object 0x30 calls them 4/9.
    assert protocol.encode_sparse_positions({15: 0x80, 16: 0x81}) == bytes.fromhex(
        "04 80 09 81"
    )
    assert protocol.encode_sparse_positions({0: 0x40, 1: 0x50}) == bytes.fromhex(
        "00 40 01 50"
    )


def test_sparse_positions_reject_invalid_and_oversized_input() -> None:
    with pytest.raises(ValidationError, match="must not be empty"):
        protocol.encode_sparse_positions({})
    with pytest.raises(ValidationError, match="physical"):
        protocol.encode_sparse_positions({20: 0})


def test_i16_position_block_is_little_endian_and_signed() -> None:
    values = [-32768, -2, -1, 0, 1, 32767] + list(range(30))
    payload = b"".join(value.to_bytes(2, "little", signed=True) for value in values)

    assert protocol.decode_i16_position_block(payload) == (
        values[0],
        *values[5:15],
        *values[16:25],
    )


def test_i16_position_block_rejects_truncation() -> None:
    with pytest.raises(HandProtocolError, match="expected 72"):
        protocol.decode_i16_position_block(bytes(71))
