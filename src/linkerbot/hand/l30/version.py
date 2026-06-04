"""Device identity and version queries for L30."""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum

from . import protocol
from .client import L30Client

_DEVICE_INFO_PRODUCT_ID_INDEX = 0
_DEVICE_INFO_SERIAL_START = 1
_DEVICE_INFO_SERIAL_END = 5
_DEVICE_INFO_SOFTWARE_START = 5
_DEVICE_INFO_HARDWARE_START = 8
_DEVICE_INFO_STRUCTURE_START = 11
_DEVICE_INFO_NODE_ID_INDEX = 14
_DEVICE_INFO_HAND_TYPE_INDEX = 15
_DEVICE_INFO_SENSOR_TYPE_INDEX = 16
_DEVICE_INFO_ORIGIN_INDEX = 17
_VERSION_BYTE_COUNT = 3
_HAND_TYPE_LEFT = 0
_HAND_TYPE_RIGHT = 1
_DEFAULT_QUERY_TIMEOUT_MS = 1000


class L30HandSide(str, Enum):
    """Physical L30 hand side reported by the device coding information."""

    LEFT = "left"
    RIGHT = "right"


@dataclass(frozen=True, slots=True)
class L30Version:
    """L30 semantic version number.

    Attributes:
        major: Major version number.
        minor: Minor version number.
        patch: Patch/revision number.
    """

    major: int
    minor: int
    patch: int

    def __str__(self) -> str:
        """Return version string in format 'V{major}.{minor}.{patch}'."""
        return f"V{self.major}.{self.minor}.{self.patch}"


@dataclass(frozen=True, slots=True)
class L30DeviceInfo:
    """Complete L30 coding and version information.

    Attributes:
        product_id: Product identifier reported by DeviceInfo.
        serial_number: Numeric serial number encoded as uint32 big-endian.
        software_version: Embedded software version.
        hardware_version: PCB/hardware version.
        structure_version: Mechanical/structure version.
        node_id: Device NodeID currently reported by the hand.
        hand_side: Physical hand side reported by production coding.
        sensor_type: One-character tactile sensor type code.
        origin: One-character origin/factory code.
        timestamp: Unix timestamp when the data was retrieved.
    """

    product_id: int
    serial_number: int
    software_version: L30Version
    hardware_version: L30Version
    structure_version: L30Version
    node_id: int
    hand_side: L30HandSide
    sensor_type: str
    origin: str
    timestamp: float


class VersionManager:
    """Manager for L30 read-only device coding and version queries."""

    def __init__(self, client: L30Client) -> None:
        """Initialize the version manager.

        Args:
            client: L30 protocol client used to send config read commands.
        """
        self._client = client

    def get_device_info(
        self, *, timeout_ms: float = _DEFAULT_QUERY_TIMEOUT_MS
    ) -> L30DeviceInfo:
        """Read the complete L30 DeviceInfo structure.

        Returns:
            L30DeviceInfo containing product ID, serial number, versions, NodeID,
            physical hand side, sensor type, and origin code.
        """
        response = self._client.read(
            parent=protocol.L30_PARENT_CONFIG,
            subcmd=protocol.L30_SUBCMD_DEVICE_INFO,
            timeout_ms=timeout_ms,
        )
        payload = protocol.decode_response_payload(
            response, expected_length=protocol.L30_DEVICE_INFO_BYTE_LENGTH
        )
        return L30DeviceInfo(
            product_id=payload[_DEVICE_INFO_PRODUCT_ID_INDEX],
            serial_number=int.from_bytes(
                payload[_DEVICE_INFO_SERIAL_START:_DEVICE_INFO_SERIAL_END], "big"
            ),
            software_version=_decode_version(payload, _DEVICE_INFO_SOFTWARE_START),
            hardware_version=_decode_version(payload, _DEVICE_INFO_HARDWARE_START),
            structure_version=_decode_version(payload, _DEVICE_INFO_STRUCTURE_START),
            node_id=payload[_DEVICE_INFO_NODE_ID_INDEX],
            hand_side=_decode_hand_side(payload[_DEVICE_INFO_HAND_TYPE_INDEX]),
            sensor_type=_decode_ascii_byte(payload[_DEVICE_INFO_SENSOR_TYPE_INDEX]),
            origin=_decode_ascii_byte(payload[_DEVICE_INFO_ORIGIN_INDEX]),
            timestamp=time.time(),
        )

    def get_product_code(self, *, timeout_ms: float = _DEFAULT_QUERY_TIMEOUT_MS) -> str:
        """Read the ASCII production code string.

        Returns:
            Product code such as ``LHT30-06-001-L-B-3-A``.
        """
        response = self._client.read(
            parent=protocol.L30_PARENT_CONFIG,
            subcmd=protocol.L30_SUBCMD_PRODUCT_CODE,
            timeout_ms=timeout_ms,
        )
        return protocol.decode_ascii_response(response)

    def get_node_id(self, *, timeout_ms: float = _DEFAULT_QUERY_TIMEOUT_MS) -> int:
        """Read the current L30 NodeID from device coding information."""
        response = self._client.read(
            parent=protocol.L30_PARENT_CONFIG,
            subcmd=protocol.L30_SUBCMD_NODE_ID,
            timeout_ms=timeout_ms,
        )
        payload = protocol.decode_response_payload(response, expected_length=1)
        return payload[0]

    def get_hand_side(
        self, *, timeout_ms: float = _DEFAULT_QUERY_TIMEOUT_MS
    ) -> L30HandSide:
        """Read whether the device is coded as left or right hand."""
        response = self._client.read(
            parent=protocol.L30_PARENT_CONFIG,
            subcmd=protocol.L30_SUBCMD_HAND_TYPE,
            timeout_ms=timeout_ms,
        )
        payload = protocol.decode_response_payload(response, expected_length=1)
        return _decode_hand_side(payload[0])


def _decode_version(payload: bytes, start: int) -> L30Version:
    version = payload[start : start + _VERSION_BYTE_COUNT]
    return L30Version(major=version[0], minor=version[1], patch=version[2])


def _decode_hand_side(value: int) -> L30HandSide:
    if value == _HAND_TYPE_LEFT:
        return L30HandSide.LEFT
    if value == _HAND_TYPE_RIGHT:
        return L30HandSide.RIGHT
    raise protocol.ProtocolError(f"unknown L30 hand type {value}")


def _decode_ascii_byte(value: int) -> str:
    try:
        return bytes([value]).decode("ascii")
    except UnicodeDecodeError as error:
        raise protocol.ProtocolError("DeviceInfo byte is not valid ASCII") from error
