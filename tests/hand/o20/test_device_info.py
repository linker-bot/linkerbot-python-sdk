from __future__ import annotations

import pytest

from linkerbot.hand.o20 import protocol
from linkerbot.hand.o20.client import O20Client
from linkerbot.hand.o20.protocol import ProtocolError
from linkerbot.hand.o20.version import O20HandSide, VersionManager
from tests.hand.o20.fakes import FakeDispatcher

pytestmark = [pytest.mark.o20, pytest.mark.canfd]


def _build_device_info_payload(
    *,
    product: bytes,
    serial: bytes,
    software: bytes,
    hardware: bytes,
    hand_type: int,
    unique_id: bytes,
) -> bytes:
    return (
        product.ljust(protocol.O20_DEVICE_INFO_PRODUCT_LENGTH, b"\x00")
        + serial.ljust(protocol.O20_DEVICE_INFO_SERIAL_LENGTH, b"\x00")
        + software.ljust(protocol.O20_DEVICE_INFO_SOFTWARE_LENGTH, b"\x00")
        + hardware.ljust(protocol.O20_DEVICE_INFO_HARDWARE_LENGTH, b"\x00")
        + bytes([hand_type])
        + unique_id.ljust(protocol.O20_DEVICE_INFO_UID_LENGTH, b"\x00")
    )


def test_device_info_decodes_all_fields_from_62_byte_payload() -> None:
    unique_id = bytes(range(protocol.O20_DEVICE_INFO_UID_LENGTH))
    payload = _build_device_info_payload(
        product=b"O20-R",
        serial=b"SN-2026-0001",
        software=b"V1.0.0",
        hardware=b"H1.0.0",
        hand_type=protocol.O20_HAND_TYPE_RIGHT,
        unique_id=unique_id,
    )
    dispatcher = FakeDispatcher(responses={protocol.O20_REG_DEVICE_INFO: payload})
    manager = VersionManager(O20Client(dispatcher, device_id=0x01))

    info = manager.get_device_info(timeout_ms=200)

    assert info.product_model == "O20-R"
    assert info.serial_number == "SN-2026-0001"
    assert info.software_version == "V1.0.0"
    assert info.hardware_version == "H1.0.0"
    assert info.hand_side is O20HandSide.RIGHT
    assert info.unique_id == unique_id


def test_device_info_decodes_left_hand_side() -> None:
    payload = _build_device_info_payload(
        product=b"O20-L",
        serial=b"SN",
        software=b"V1",
        hardware=b"H1",
        hand_type=protocol.O20_HAND_TYPE_LEFT,
        unique_id=bytes(protocol.O20_DEVICE_INFO_UID_LENGTH),
    )
    dispatcher = FakeDispatcher(responses={protocol.O20_REG_DEVICE_INFO: payload})
    manager = VersionManager(O20Client(dispatcher, device_id=0x02))

    info = manager.get_device_info(timeout_ms=200)

    assert info.hand_side is O20HandSide.LEFT


def test_device_info_rejects_unknown_hand_type() -> None:
    payload = _build_device_info_payload(
        product=b"O20",
        serial=b"SN",
        software=b"V1",
        hardware=b"H1",
        hand_type=0x7F,
        unique_id=bytes(protocol.O20_DEVICE_INFO_UID_LENGTH),
    )
    dispatcher = FakeDispatcher(responses={protocol.O20_REG_DEVICE_INFO: payload})
    manager = VersionManager(O20Client(dispatcher, device_id=0x01))

    with pytest.raises(ProtocolError, match="hand type"):
        manager.get_device_info(timeout_ms=200)


def test_device_info_rejects_short_response() -> None:
    dispatcher = FakeDispatcher(responses={protocol.O20_REG_DEVICE_INFO: bytes(50)})
    manager = VersionManager(O20Client(dispatcher, device_id=0x01))

    with pytest.raises(ProtocolError, match="too short"):
        manager.get_device_info(timeout_ms=200)
