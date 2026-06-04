import pytest

from linkerbot.exceptions import ValidationError
from linkerbot.hand.l30 import protocol
from linkerbot.hand.l30.protocol import (
    L30_ACCESS_READ,
    L30_ACCESS_WRITE,
    L30_PARENT_CONTROL,
    L30_PARENT_PERIODIC,
    L30_PARENT_QUERY,
    L30_SUBCMD_DISABLE,
    L30_SUBCMD_ENABLE,
    L30_SUBCMD_POSITION,
    L30FrameId,
    ProtocolError,
)

pytestmark = [pytest.mark.l30, pytest.mark.canfd]


def test_build_can_id_matches_v2_golden_vectors() -> None:
    assert (
        _can_id(L30_ACCESS_WRITE, L30_PARENT_CONTROL, L30_SUBCMD_ENABLE) == 0x0220E100
    )
    assert _response_id(0x0220E100) == 0x0220E008
    assert (
        _can_id(L30_ACCESS_WRITE, L30_PARENT_CONTROL, L30_SUBCMD_DISABLE) == 0x02210100
    )
    assert _response_id(0x02210100) == 0x02210008
    assert (
        _can_id(L30_ACCESS_WRITE, L30_PARENT_CONTROL, L30_SUBCMD_POSITION) == 0x02202100
    )
    assert _can_id(L30_ACCESS_WRITE, L30_PARENT_CONTROL, 0x02) == 0x02204100
    assert _can_id(L30_ACCESS_WRITE, L30_PARENT_CONTROL, 0x03) == 0x02206100
    assert _can_id(L30_ACCESS_READ, L30_PARENT_QUERY, L30_SUBCMD_POSITION) == 0x00A02100
    assert _response_id(0x00A02100) == 0x00A02008
    assert (
        _can_id(L30_ACCESS_WRITE, L30_PARENT_PERIODIC, L30_SUBCMD_POSITION)
        == 0x02802100
    )
    assert _response_id(0x02802100) == 0x02802008
    assert (
        _can_id(
            L30_ACCESS_READ,
            L30_PARENT_PERIODIC,
            L30_SUBCMD_POSITION,
            dst_id=0,
            src_id=1,
        )
        == 0x00802008
    )


def test_parse_can_id_round_trips_fields() -> None:
    frame_id = protocol.parse_can_id(0x0220E100)

    assert frame_id == L30FrameId(
        priority=0,
        access=1,
        parent=1,
        subcmd=7,
        dst_id=1,
        src_id=0,
    )
    assert frame_id.to_int() == 0x0220E100


@pytest.mark.parametrize(
    "kwargs",
    [
        {"priority": 8},
        {"access": 2},
        {"parent": 16},
        {"subcmd": 256},
        {"dst_id": 32},
        {"src_id": 32},
    ],
)
def test_build_can_id_rejects_invalid_fields(kwargs: dict[str, int]) -> None:
    valid = {
        "priority": 0,
        "access": 1,
        "parent": 1,
        "subcmd": 1,
        "dst_id": 1,
        "src_id": 0,
    }
    valid.update(kwargs)

    with pytest.raises(ValidationError):
        protocol.build_can_id(**valid)


def test_parse_can_id_rejects_reserved_low_bits() -> None:
    with pytest.raises(ValidationError, match="reserved"):
        protocol.parse_can_id(0x0220E101)


def test_encode_i16_vector_uses_big_endian_payload() -> None:
    payload = protocol.encode_i16_vector([100] * protocol.L30_JOINT_COUNT)

    assert payload[:2] == bytes([0x22, 0x00])
    assert payload[2:] == b"\x00\x64" * protocol.L30_JOINT_COUNT
    assert len(payload) == 36


def test_encode_u16_vector_validates_range() -> None:
    assert (
        protocol.encode_u16_vector(
            [60] * protocol.L30_JOINT_COUNT, minimum=60, maximum=800
        )[2:]
        == b"\x00\x3c" * 17
    )
    with pytest.raises(ValidationError):
        protocol.encode_u16_vector(
            [59] * protocol.L30_JOINT_COUNT, minimum=60, maximum=800
        )


def test_decode_i16_response_checks_status_and_decodes_data() -> None:
    response = bytes([0x22, 0x00, 0x00]) + b"\x00\x01" * protocol.L30_JOINT_COUNT

    assert protocol.decode_i16_response(response) == (1,) * protocol.L30_JOINT_COUNT


def test_decode_responses_validate_declared_length_and_allow_padding() -> None:
    i16_response = (
        bytes([0x22, 0x00, 0x00]) + b"\x00\x01" * protocol.L30_JOINT_COUNT + bytes(10)
    )
    u8_response = bytes([0x11, 0x00, 0x00]) + bytes(range(17)) + bytes(10)

    assert protocol.decode_i16_response(i16_response) == (1,) * protocol.L30_JOINT_COUNT
    assert protocol.decode_u8_response(u8_response) == tuple(range(17))

    with pytest.raises(protocol.ProtocolError, match="length mismatch"):
        protocol.decode_i16_response(bytes([0x00, 0x00, 0x00]) + b"\x00\x01" * 17)
    with pytest.raises(protocol.ProtocolError, match="payload too short"):
        protocol.decode_u8_response(bytes([0x11, 0x00, 0x00]) + bytes(range(16)))
    with pytest.raises(protocol.ProtocolError, match="transaction"):
        protocol.decode_u8_response(bytes([0x11, 0x10, 0x00]) + bytes(range(17)))


@pytest.mark.parametrize("status", [0x10, 0x20, 0x35, 0xF0])
def test_check_response_status_raises_readable_protocol_error(status: int) -> None:
    with pytest.raises(ProtocolError, match=f"0x{status:02X}"):
        protocol.check_response_status(bytes([0x00, 0x00, status]))


def test_decode_response_payload_returns_declared_payload() -> None:
    payload = bytes(range(protocol.L30_DEVICE_INFO_BYTE_LENGTH))
    response = bytes([protocol.L30_DEVICE_INFO_BYTE_LENGTH, 0x00, 0x00]) + payload

    assert (
        protocol.decode_response_payload(
            response, expected_length=protocol.L30_DEVICE_INFO_BYTE_LENGTH
        )
        == payload
    )


def test_decode_ascii_response_validates_status_and_encoding() -> None:
    product_code = b"LHT30-06-001-L-B-3-A"

    assert protocol.decode_ascii_response(
        bytes([len(product_code), 0, 0]) + product_code
    ) == ("LHT30-06-001-L-B-3-A")
    with pytest.raises(protocol.ProtocolError, match="0x20"):
        protocol.decode_ascii_response(bytes([0x00, 0x00, 0x20]))
    with pytest.raises(protocol.ProtocolError, match="ASCII"):
        protocol.decode_ascii_response(bytes([1, 0, 0, 0xFF]))


def test_encode_periodic_config_matches_v2_golden_vector() -> None:
    payload = protocol.encode_periodic_config(
        enabled=True, period_ms=20, joint_mask=0x00000003
    )

    assert payload == bytes.fromhex("09 00 01 00 00 00 14 00 00 00 03")


def test_encode_periodic_config_validates_period_and_mask() -> None:
    with pytest.raises(ValidationError):
        protocol.encode_periodic_config(enabled=True, period_ms=19)
    with pytest.raises(ValidationError):
        protocol.encode_periodic_config(enabled=True, period_ms=20, joint_mask=1 << 17)


def test_decode_periodic_reports() -> None:
    i16_report = bytes([4, 0]) + b"\x00\x01\x00\x02"
    u8_report = bytes([2, 0, 3, 4])

    assert protocol.decode_periodic_i16_report(i16_report, joint_mask=0b11) == (1, 2)
    assert protocol.decode_periodic_u8_report(u8_report, joint_mask=0b11) == (3, 4)


def test_assemble_tactile_payload_from_two_frames() -> None:
    first_segment = bytes(range(61))
    second_segment = bytes(range(61, 72))
    first_frame = bytes([61, 0x10, 0x00]) + first_segment
    second_frame = bytes([11, 0x11, 0x00]) + second_segment

    assert protocol.assemble_tactile_payload(first_frame, second_frame) == bytes(
        range(72)
    )


def test_assemble_tactile_payload_ignores_canfd_padding() -> None:
    first_segment = bytes(range(61))
    second_segment = bytes(range(61, 72))
    first_frame = bytes([61, 0x10, 0x00]) + first_segment + bytes(3)
    second_frame = bytes([11, 0x11, 0x00]) + second_segment + bytes(53)

    assert protocol.assemble_tactile_payload(first_frame, second_frame) == bytes(
        range(72)
    )


def test_assemble_tactile_payload_rejects_wrong_sequence() -> None:
    first_frame = bytes([61, 0x11, 0x00]) + bytes(61)
    second_frame = bytes([11, 0x10, 0x00]) + bytes(11)

    with pytest.raises(ProtocolError, match="transaction"):
        protocol.assemble_tactile_payload(first_frame, second_frame)


def _can_id(
    access: int, parent: int, subcmd: int, *, dst_id: int = 1, src_id: int = 0
) -> int:
    return protocol.build_can_id(
        priority=0,
        access=access,
        parent=parent,
        subcmd=subcmd,
        dst_id=dst_id,
        src_id=src_id,
    )


def _response_id(request_id: int) -> int:
    return protocol.expected_response_id(request_id)
