"""Read-only product information for O30 object ``0x41``."""

from __future__ import annotations

import time
from dataclasses import dataclass

from linkerbot.hand.hand_protocol_v1 import HandProtocolError, HandProtocolV1

from . import protocol


@dataclass(frozen=True, slots=True)
class O30DeviceInfo:
    """Decoded 225-byte O30 product-information object."""

    product_model: str
    voltage_range: str
    mcu_uid: str
    device_uid: str
    protocol_name: str
    protocol_version: str
    interface_hardware_version: str
    adapter_hardware_version: str
    controller_hardware_version: str
    bootloader_version: str
    application_version: str
    mechanical_version: str
    compile_time: str
    supported_interfaces: str
    hand_info: bytes
    timestamp: float


class VersionManager:
    """Read complete O30 identity/version data without exposing writes."""

    def __init__(self, client: HandProtocolV1) -> None:
        self._client = client

    def get_device_info(self, *, timeout_ms: float = 1000) -> O30DeviceInfo:
        payload = self._client.read(
            main_index=protocol.O30_MI_PRODUCT_INFO,
            length=protocol.O30_PRODUCT_INFO_BYTE_LENGTH,
            timeout_ms=timeout_ms,
        )
        return decode_device_info(payload)


def decode_device_info(payload: bytes) -> O30DeviceInfo:
    """Decode the fixed offsets verified for product object ``0x41``."""
    normalized = bytes(payload)
    if len(normalized) < protocol.O30_PRODUCT_INFO_BYTE_LENGTH:
        raise HandProtocolError(
            "O30 product info too short: expected "
            f"{protocol.O30_PRODUCT_INFO_BYTE_LENGTH} bytes, got {len(normalized)}"
        )
    data = normalized[: protocol.O30_PRODUCT_INFO_BYTE_LENGTH]
    return O30DeviceInfo(
        product_model=_decode_ascii(data[0x00:0x10]),
        voltage_range=_decode_ascii(data[0x10:0x20]),
        mcu_uid=_decode_ascii(data[0x20:0x39]),
        device_uid=_decode_ascii(data[0x39:0x59]),
        protocol_name=_decode_ascii(data[0x59:0x61]),
        protocol_version=_decode_ascii(data[0x61:0x69]),
        interface_hardware_version=_decode_ascii(data[0x69:0x71]),
        adapter_hardware_version=_decode_ascii(data[0x71:0x79]),
        controller_hardware_version=_decode_ascii(data[0x79:0x81]),
        bootloader_version=_decode_ascii(data[0x81:0x89]),
        application_version=_decode_ascii(data[0x89:0x91]),
        mechanical_version=_decode_ascii(data[0x91:0x99]),
        compile_time=_decode_ascii(data[0x99:0xB9]),
        supported_interfaces=_decode_ascii(data[0xB9:0xD9]),
        hand_info=bytes(data[0xD9:0xE1]),
        timestamp=time.time(),
    )


def _decode_ascii(data: bytes) -> str:
    return bytes(data).split(b"\x00", 1)[0].decode("ascii", errors="replace").strip()


# Backward-compatible aliases for the former model name.
O30iDeviceInfo = O30DeviceInfo
