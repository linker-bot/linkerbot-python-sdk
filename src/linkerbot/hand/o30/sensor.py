"""O30 sensor-capability metadata from HOP object ``0x31``."""

from __future__ import annotations

import time
from dataclasses import dataclass

from linkerbot.hand.hand_protocol_v1 import HandProtocolError, HandProtocolV1

from . import protocol


@dataclass(frozen=True, slots=True)
class O30SensorInfo:
    """Measured sensor descriptor; current O30 units may report NO_SENSOR."""

    sensor_type: str
    unit: str
    total_data_length: int
    selected_sensor: int
    rows: int
    columns: int
    metadata: bytes
    timestamp: float

    @property
    def has_sensor_data(self) -> bool:
        return self.total_data_length > 0


class SensorManager:
    """Read sensor metadata before attempting any dynamic data channels."""

    def __init__(self, client: HandProtocolV1) -> None:
        self._client = client

    def get_info(self, *, timeout_ms: float = 1000) -> O30SensorInfo:
        payload = self._client.read(
            main_index=protocol.O30_MI_SENSOR_INFO,
            length=protocol.O30_SENSOR_INFO_BYTE_LENGTH,
            timeout_ms=timeout_ms,
        )
        return decode_sensor_info(payload)


def decode_sensor_info(payload: bytes) -> O30SensorInfo:
    normalized = bytes(payload)
    if len(normalized) < protocol.O30_SENSOR_INFO_BYTE_LENGTH:
        raise HandProtocolError(
            "O30 sensor info too short: expected "
            f"{protocol.O30_SENSOR_INFO_BYTE_LENGTH} bytes, got {len(normalized)}"
        )
    data = normalized[: protocol.O30_SENSOR_INFO_BYTE_LENGTH]
    return O30SensorInfo(
        sensor_type=_decode_ascii(data[0x00:0x20]),
        unit=_decode_ascii(data[0x20:0x28]),
        total_data_length=int.from_bytes(data[0x2B:0x2D], "little"),
        selected_sensor=data[0x2D],
        rows=data[0x2E],
        columns=data[0x2F],
        metadata=bytes(data[0x28:0x32]),
        timestamp=time.time(),
    )


def _decode_ascii(data: bytes) -> str:
    return bytes(data).split(b"\x00", 1)[0].decode("ascii", errors="replace").strip()


# Backward-compatible aliases for the former model name.
O30iSensorInfo = O30SensorInfo
