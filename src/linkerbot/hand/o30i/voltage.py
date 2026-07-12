"""Voltage-state sensing for O30i."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from linkerbot.hand.hand_protocol_v1 import HandProtocolV1
from linkerbot.relay import DataRelay

from . import protocol
from ._runtime import read_vector


@dataclass(frozen=True, slots=True)
class O30iVoltageData:
    voltages: tuple[int, ...]
    timestamp: float


class VoltageManager:
    """Read voltage object ``0x05``; writes are intentionally not exposed."""

    def __init__(self, client: HandProtocolV1) -> None:
        self._client = client
        self._relay = DataRelay[O30iVoltageData]()

    def get_blocking(self, timeout_ms: float = 100) -> O30iVoltageData:
        data = O30iVoltageData(
            voltages=read_vector(
                self._client,
                main_index=protocol.O30I_MI_VOLTAGE,
                timeout_ms=timeout_ms,
            ),
            timestamp=time.time(),
        )
        self._relay.push(data)
        return data

    def get_snapshot(self) -> O30iVoltageData | None:
        return self._relay.snapshot()

    def _send_sense_request(self) -> None:
        self.get_blocking(timeout_ms=100)

    def _set_event_sink(self, sink: Callable[[O30iVoltageData], None]) -> None:
        self._relay.set_sink(sink)

    def close(self) -> None:
        """Release manager resources; this manager owns no threads."""
