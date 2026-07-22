import pytest

from linkerbot.exceptions import ValidationError
from linkerbot.hand.o20 import protocol
from linkerbot.hand.o20.protocol import O20FrameId, ProtocolError

pytestmark = [pytest.mark.o20, pytest.mark.canfd]


def test_build_can_id_matches_ticket_golden_vectors() -> None:
    assert (
        protocol.build_can_id(device_id=0x01, register=0x06, write=True) == 0x0020D000
    )
    assert (
        protocol.build_can_id(device_id=0x01, register=0x03, write=False) == 0x00206000
    )
    assert (
        protocol.build_can_id(device_id=0x02, register=0x06, write=True) == 0x0040D000
    )
    assert (
        protocol.build_can_id(device_id=0x01, register=0x00, write=False) == 0x00200000
    )


def test_parse_can_id_round_trips_fields() -> None:
    frame_id = protocol.parse_can_id(0x0020D000)

    assert frame_id == O20FrameId(device_id=1, register=0x06, write=1)
    assert frame_id.to_int() == 0x0020D000


@pytest.mark.parametrize(
    "kwargs",
    [
        {"device_id": -1},
        {"device_id": 256},
        {"register": -1},
        {"register": 256},
    ],
)
def test_build_can_id_rejects_invalid_fields(kwargs: dict[str, int]) -> None:
    valid = {"device_id": 1, "register": 0x06}
    valid.update(kwargs)

    with pytest.raises(ValidationError):
        protocol.build_can_id(
            device_id=valid["device_id"], register=valid["register"], write=True
        )


def test_parse_can_id_rejects_reserved_low_bits() -> None:
    with pytest.raises(ValidationError, match="reserved"):
        protocol.parse_can_id(0x0020D001)


def test_encode_i16_vector_uses_little_endian_with_reserved_zero_slot() -> None:
    payload = protocol.encode_i16_vector([1] * protocol.O20_JOINT_COUNT)

    assert len(payload) == 34
    assert payload[:32] == b"\x01\x00" * 16
    assert payload[32:] == b"\x00\x00"


def test_encode_i16_vector_validates_count() -> None:
    with pytest.raises(ValidationError):
        protocol.encode_i16_vector([0] * 17)
    with pytest.raises(ValidationError):
        protocol.encode_i16_vector([0] * 15)


def test_encode_i16_vector_handles_signed_values() -> None:
    values = [-1] * protocol.O20_JOINT_COUNT
    payload = protocol.encode_i16_vector(values)

    assert payload[:32] == b"\xff\xff" * 16
    assert payload[32:] == b"\x00\x00"


def test_encode_u16_vector_validates_range_and_zeros_reserved_slot() -> None:
    payload = protocol.encode_u16_vector(
        [400] * protocol.O20_JOINT_COUNT, minimum=0, maximum=1000
    )

    assert payload[:32] == b"\x90\x01" * 16
    assert payload[32:] == b"\x00\x00"
    with pytest.raises(ValidationError):
        protocol.encode_u16_vector(
            [1001] * protocol.O20_JOINT_COUNT, minimum=0, maximum=1000
        )


def test_encode_u8_vector_zero_pads_reserved_slot() -> None:
    payload = protocol.encode_u8_vector([5] * protocol.O20_JOINT_COUNT)

    assert len(payload) == 17
    assert payload[:16] == b"\x05" * 16
    assert payload[16:] == b"\x00"


def test_decode_i16_vector_response_drops_seventeenth_reserved_slot() -> None:
    response = b"".join(
        value.to_bytes(2, "little", signed=True)
        for value in [*range(1, 17), 0xFFFF & 999]
    )

    decoded = protocol.decode_i16_vector_response(response)

    assert decoded == tuple(range(1, 17))


def test_decode_u16_vector_response_drops_seventeenth_reserved_slot() -> None:
    response = b"".join(
        value.to_bytes(2, "little", signed=False) for value in [*range(1, 17), 12345]
    )

    decoded = protocol.decode_u16_vector_response(response)

    assert decoded == tuple(range(1, 17))


def test_decode_u8_vector_response_drops_seventeenth_reserved_slot() -> None:
    response = bytes(range(20))

    decoded = protocol.decode_u8_vector_response(response)

    assert decoded == tuple(range(16))


def test_decode_vector_responses_reject_short_payload() -> None:
    with pytest.raises(ProtocolError, match="too short"):
        protocol.decode_i16_vector_response(b"\x00" * 33)
    with pytest.raises(ProtocolError, match="too short"):
        protocol.decode_u16_vector_response(b"\x00" * 33)
    with pytest.raises(ProtocolError, match="too short"):
        protocol.decode_u8_vector_response(b"\x00" * 16)


def test_assemble_tactile_payload_combines_64_and_9_byte_segments() -> None:
    data1 = bytes([0x01]) + bytes(range(63))
    data2 = bytes(range(63, 72)) + bytes(64)

    online, matrix = protocol.assemble_tactile_payload(
        data1, data2[: protocol.O20_TACTILE_DATA2_LENGTH]
    )

    assert online is True
    assert len(matrix) == protocol.O20_TACTILE_MATRIX_LENGTH
    assert matrix == bytes(range(72))


def test_assemble_tactile_payload_reads_offline_flag() -> None:
    data1 = bytes(64)
    data2 = bytes(9)

    online, matrix = protocol.assemble_tactile_payload(data1, data2)

    assert online is False
    assert matrix == bytes(72)


def test_assemble_tactile_payload_rejects_short_segments() -> None:
    with pytest.raises(ProtocolError, match="DATA1"):
        protocol.assemble_tactile_payload(bytes(63), bytes(9))
    with pytest.raises(ProtocolError, match="DATA2"):
        protocol.assemble_tactile_payload(bytes(64), bytes(8))


def test_assemble_tactile_payload_rejects_unexpected_online_byte() -> None:
    """Online flag must be exactly 0 or 1; other values likely indicate a
    framing or wiring problem and must not be silently coerced to True."""
    data1 = bytes([0x02]) + bytes(63)
    data2 = bytes(9)

    with pytest.raises(ProtocolError, match="online flag"):
        protocol.assemble_tactile_payload(data1, data2)


def test_build_message_returns_extended_frame_with_optional_dlc() -> None:
    message = protocol.build_message(
        device_id=0x01,
        register=protocol.O20_REG_TARGET_POS,
        write=True,
        data=b"\x01\x02",
        dlc=protocol.O20_VECTOR_DLC,
    )

    assert message.arbitration_id == 0x0020D000
    assert message.is_extended_id is True
    assert message.data == b"\x01\x02"
    assert message.dlc == protocol.O20_VECTOR_DLC


def test_build_message_for_read_uses_empty_payload_and_zero_dlc() -> None:
    message = protocol.build_message(
        device_id=0x01,
        register=protocol.O20_REG_CURRENT_POS,
        write=False,
        dlc=protocol.O20_EMPTY_REQUEST_DLC,
    )

    assert message.arbitration_id == 0x00206000
    assert message.data == b""
    assert message.dlc == 0


def test_validate_range_accepts_intenum_but_rejects_bool() -> None:
    """O20Register and other int subclasses must pass through validation —
    we want users to pass O20Register.CURRENT_POS to client.read(register=...).
    bool is also an int subclass in Python and is explicitly rejected so it
    cannot sneak through as 0/1."""
    from linkerbot.hand.o20 import O20Register

    protocol._validate_range(
        O20Register.CURRENT_POS, "register", 0, protocol.O20_REGISTER_MAX
    )
    protocol._validate_range(0, "register", 0, protocol.O20_REGISTER_MAX)

    with pytest.raises(ValidationError, match="must be int"):
        protocol._validate_range(True, "register", 0, protocol.O20_REGISTER_MAX)
    with pytest.raises(ValidationError, match="must be int"):
        protocol._validate_range(
            "0x06",
            "register",
            0,
            protocol.O20_REGISTER_MAX,
        )


def test_client_read_accepts_intenum_register(monkeypatch) -> None:
    """End-to-end: passing an O20Register member to client.read() must not
    raise ValidationError on the register argument."""
    from linkerbot.hand.o20 import O20Register
    from linkerbot.hand.o20.client import O20Client
    from tests.hand.o20.fakes import FakeDispatcher

    payload = b"\x00\x00" * protocol.O20_FRAME_VECTOR_COUNT
    dispatcher = FakeDispatcher(responses={int(O20Register.CURRENT_POS): payload})
    client = O20Client(dispatcher, device_id=0x01)

    response = client.read(register=O20Register.CURRENT_POS, timeout_ms=200)

    assert response == payload
