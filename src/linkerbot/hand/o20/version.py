"""Device identity queries for O20.

The O20 hand exposes a 62-byte DeviceInfo register (``0x00``) that combines:

* product model (10 bytes ASCII)
* serial number (20 bytes ASCII)
* software version (10 bytes ASCII)
* hardware version (10 bytes ASCII)
* hand type byte (1 = right, 2 = left — matches the CAN ``device_id``)
* unique identifier (11 bytes)

The total length is binding per the protocol's ``uint8_t[62]`` declaration; the
remaining UID bytes are taken from what fits inside that contract.

The version manager exposes only read access; writes to the device-information
modification register (``0x6E``) are intentionally not part of the public SDK.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum

from . import protocol
from .client import O20Client

_DEFAULT_QUERY_TIMEOUT_MS = 1000


class O20HandSide(str, Enum):
    """Physical O20 hand side reported by DeviceInfo."""

    LEFT = "left"
    RIGHT = "right"


@dataclass(frozen=True, slots=True)
class O20DeviceInfo:
    """Complete O20 DeviceInfo data.

    Attributes:
        product_model: Product model string reported by DeviceInfo.
        serial_number: Production serial number string.
        software_version: Embedded software version string.
        hardware_version: PCB/hardware version string.
        hand_side: Physical hand side reported by production coding.
        unique_id: 11-byte unique device identifier.
        timestamp: Unix timestamp when the data was retrieved.
    """

    product_model: str
    serial_number: str
    software_version: str
    hardware_version: str
    hand_side: O20HandSide
    unique_id: bytes
    timestamp: float


class VersionManager:
    """Manager for O20 read-only DeviceInfo queries."""

    def __init__(self, client: O20Client) -> None:
        """Initialize the version manager.

        Args:
            client: O20 protocol client used to read DeviceInfo.
        """
        self._client = client

    def get_device_info(
        self, *, timeout_ms: float = _DEFAULT_QUERY_TIMEOUT_MS
    ) -> O20DeviceInfo:
        """Read the full DeviceInfo block from register 0x00.

        Args:
            timeout_ms: Time to wait for the DeviceInfo response.

        Returns:
            O20DeviceInfo containing model, serial, version strings, hand side,
            and unique ID bytes.

        Raises:
            TimeoutError: If no matching response arrives before the timeout.
            ProtocolError: If the response payload is shorter than expected or
                contains an unknown hand-type byte.
        """
        response = self._client.read(
            register=protocol.O20_REG_DEVICE_INFO, timeout_ms=timeout_ms
        )
        if len(response) < protocol.O20_DEVICE_INFO_BYTE_LENGTH:
            raise protocol.ProtocolError(
                f"DeviceInfo response too short: expected "
                f"{protocol.O20_DEVICE_INFO_BYTE_LENGTH} bytes, got {len(response)}"
            )
        payload = response[: protocol.O20_DEVICE_INFO_BYTE_LENGTH]
        cursor = 0
        product_model = _decode_ascii(
            payload[cursor : cursor + protocol.O20_DEVICE_INFO_PRODUCT_LENGTH]
        )
        cursor += protocol.O20_DEVICE_INFO_PRODUCT_LENGTH
        serial_number = _decode_ascii(
            payload[cursor : cursor + protocol.O20_DEVICE_INFO_SERIAL_LENGTH]
        )
        cursor += protocol.O20_DEVICE_INFO_SERIAL_LENGTH
        software_version = _decode_ascii(
            payload[cursor : cursor + protocol.O20_DEVICE_INFO_SOFTWARE_LENGTH]
        )
        cursor += protocol.O20_DEVICE_INFO_SOFTWARE_LENGTH
        hardware_version = _decode_ascii(
            payload[cursor : cursor + protocol.O20_DEVICE_INFO_HARDWARE_LENGTH]
        )
        cursor += protocol.O20_DEVICE_INFO_HARDWARE_LENGTH
        hand_side = _decode_hand_side(payload[cursor])
        cursor += protocol.O20_DEVICE_INFO_HAND_TYPE_LENGTH
        unique_id = bytes(
            payload[cursor : cursor + protocol.O20_DEVICE_INFO_UID_LENGTH]
        )
        return O20DeviceInfo(
            product_model=product_model,
            serial_number=serial_number,
            software_version=software_version,
            hardware_version=hardware_version,
            hand_side=hand_side,
            unique_id=unique_id,
            timestamp=time.time(),
        )


def _decode_ascii(data: bytes) -> str:
    return bytes(data).split(b"\x00", 1)[0].decode("ascii", errors="replace")


def _decode_hand_side(value: int) -> O20HandSide:
    if value == protocol.O20_HAND_TYPE_LEFT:
        return O20HandSide.LEFT
    if value == protocol.O20_HAND_TYPE_RIGHT:
        return O20HandSide.RIGHT
    raise protocol.ProtocolError(f"unknown O20 hand type {value}")
