import pytest

from linkerbot.exceptions import ValidationError
from linkerbot.hand.hand_protocol_v1 import protocol

pytestmark = [pytest.mark.o30i, pytest.mark.canfd]


def test_response_id_uses_hop_response_flag() -> None:
    assert protocol.response_id_for_request(0x001) == 0x401
    assert protocol.response_id_for_request(0x123) == 0x523


def test_response_id_rejects_request_that_cannot_fit_response_flag() -> None:
    with pytest.raises(ValidationError, match="request_id"):
        protocol.response_id_for_request(0x400)


def test_build_read_message_matches_candump_vector() -> None:
    message = protocol.build_read_message(
        request_id=0x001,
        main_index=0x01,
        sub_index=0x14,
        length=0x05,
    )

    assert message.arbitration_id == 0x001
    assert message.is_extended_id is False
    assert message.frame_type == 0x04
    assert message.data == bytes.fromhex("01 14 05")
    assert message.dlc == 3


def test_build_rts_read_sets_control_high_bit() -> None:
    message = protocol.build_read_message(
        request_id=1,
        main_index=1,
        sub_index=0x14,
        length=5,
        rts=True,
    )

    assert message.data == bytes.fromhex("81 14 05")


def test_build_write_message_matches_candump_vector() -> None:
    message = protocol.build_write_message(
        request_id=1,
        main_index=1,
        sub_index=0x14,
        payload=b"\x80" * 5,
    )

    assert message.data == bytes.fromhex("01 14 05 80 80 80 80 80")
    assert message.dlc == 8


def test_build_write_rejects_empty_and_oversized_payloads() -> None:
    with pytest.raises(ValidationError, match="must not be empty"):
        protocol.build_write_message(
            request_id=1, main_index=1, sub_index=0, payload=b""
        )
    with pytest.raises(ValidationError, match="at most 61"):
        protocol.build_write_message(
            request_id=1, main_index=1, sub_index=0, payload=bytes(62)
        )


def test_object_range_must_not_wrap_past_byte_offset_space() -> None:
    with pytest.raises(ValidationError, match="must not exceed 256"):
        protocol.build_read_message(
            request_id=1,
            main_index=1,
            sub_index=250,
            length=7,
        )


def test_decode_frame_uses_edl_and_ignores_padding() -> None:
    frame = protocol.decode_frame(bytes.fromhex("01 14 05 1C 15 16 13 11") + bytes(40))

    assert frame.main_index == 1
    assert frame.sub_index == 0x14
    assert frame.payload == bytes.fromhex("1C 15 16 13 11")
    assert frame.rts is False


def test_decode_frame_extracts_rts_without_changing_main_index() -> None:
    frame = protocol.decode_frame(bytes.fromhex("81 00 01 7F"))

    assert frame.main_index == 1
    assert frame.rts is True


def test_decode_frame_rejects_short_header_and_payload() -> None:
    with pytest.raises(protocol.HandProtocolError, match="header"):
        protocol.decode_frame(b"\x01\x00")
    with pytest.raises(protocol.HandProtocolError, match="shorter than EDL"):
        protocol.decode_frame(bytes.fromhex("01 00 05 01 02"))


def test_device_error_exposes_wire_fields() -> None:
    error = protocol.HandProtocolDeviceError(error_index=0x28, error_code=0x02)

    assert error.error_index == 0x28
    assert error.error_code == 0x02
    assert "out of range" in str(error)
