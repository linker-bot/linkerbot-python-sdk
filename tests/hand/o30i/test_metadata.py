from __future__ import annotations

import pytest

from linkerbot.hand.hand_protocol_v1 import HandProtocolError
from linkerbot.hand.o30i import O30i, protocol
from linkerbot.hand.o30i.sensor import decode_sensor_info
from linkerbot.hand.o30i.version import decode_device_info
from tests.hand.o30i.fakes import FakeO30iDispatcher

pytestmark = [pytest.mark.o30i, pytest.mark.canfd]


def _put_ascii(buffer: bytearray, start: int, length: int, text: str) -> None:
    encoded = text.encode("ascii")
    assert len(encoded) <= length
    buffer[start : start + len(encoded)] = encoded


def _product_info() -> bytes:
    data = bytearray(protocol.O30I_PRODUCT_INFO_BYTE_LENGTH)
    fields = (
        (0x00, 0x10, "O30i"),
        (0x10, 0x10, "12V~24V"),
        (0x20, 0x19, "MCU-UID-123"),
        (0x39, 0x20, "DEVICE-UID-O30I"),
        (0x59, 0x08, "HOP"),
        (0x61, 0x08, "0.0.3"),
        (0x69, 0x08, "V1.2.0"),
        (0x71, 0x08, "V1.1.0"),
        (0x79, 0x08, "V0.9.0"),
        (0x81, 0x08, "1.0.0"),
        (0x89, 0x08, "1.1.0"),
        (0x91, 0x08, "M1.0.0"),
        (0x99, 0x20, "2026-07-08 15:33:08"),
        (0xB9, 0x20, "CAN,UART"),
    )
    for start, length, text in fields:
        _put_ascii(data, start, length, text)
    data[0xD9:0xE1] = bytes.fromhex("01 02 03 04 05 06 07 08")
    return bytes(data)


def test_product_info_reads_and_reassembles_all_225_bytes() -> None:
    dispatcher = FakeO30iDispatcher({protocol.O30I_MI_PRODUCT_INFO: _product_info()})

    with O30i(dispatcher=dispatcher) as hand:
        info = hand.version.get_device_info()

    assert info.product_model == "O30i"
    assert info.protocol_name == "HOP"
    assert info.protocol_version == "0.0.3"
    assert info.application_version == "1.1.0"
    assert info.supported_interfaces == "CAN,UART"
    assert info.hand_info == bytes.fromhex("01 02 03 04 05 06 07 08")
    assert dispatcher.sent[0].data == bytes.fromhex("41 00 E1")


def test_product_info_decoder_rejects_truncation() -> None:
    with pytest.raises(HandProtocolError, match="product info too short"):
        decode_device_info(bytes(224))


def test_sensor_info_reports_no_sensor_without_reading_data_channels() -> None:
    payload = bytearray(protocol.O30I_SENSOR_INFO_BYTE_LENGTH)
    _put_ascii(payload, 0x00, 0x20, "NO_SENSOR")
    dispatcher = FakeO30iDispatcher({protocol.O30I_MI_SENSOR_INFO: bytes(payload)})

    with O30i(dispatcher=dispatcher) as hand:
        info = hand.sensor.get_info()

    assert info.sensor_type == "NO_SENSOR"
    assert info.total_data_length == 0
    assert info.has_sensor_data is False
    assert len(dispatcher.sent) == 1
    assert dispatcher.sent[0].data == bytes.fromhex("31 00 32")


def test_sensor_info_decodes_shape_and_little_endian_length() -> None:
    payload = bytearray(protocol.O30I_SENSOR_INFO_BYTE_LENGTH)
    _put_ascii(payload, 0x00, 0x20, "TACTILE")
    _put_ascii(payload, 0x20, 0x08, "raw")
    payload[0x2B:0x2D] = (0x1234).to_bytes(2, "little")
    payload[0x2D:0x30] = bytes((2, 12, 6))

    info = decode_sensor_info(bytes(payload))

    assert info.sensor_type == "TACTILE"
    assert info.unit == "raw"
    assert info.total_data_length == 0x1234
    assert info.selected_sensor == 2
    assert info.rows == 12
    assert info.columns == 6
    assert info.has_sensor_data is True


def test_diagnostics_reads_4f_as_normal_object() -> None:
    payload = bytes(range(protocol.O30I_COMMUNICATION_ERROR_BYTE_LENGTH))
    dispatcher = FakeO30iDispatcher({protocol.O30I_MI_COMMUNICATION_ERROR: payload})

    with O30i(dispatcher=dispatcher) as hand:
        errors = hand.diagnostics.get_communication_errors()

    assert errors.latest_index == 0
    assert errors.history == bytes(range(1, 17))
    assert dispatcher.sent[0].data == bytes.fromhex("4F 00 11")
