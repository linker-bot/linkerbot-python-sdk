"""Communication-error history for O30i object ``0x4F``."""

from __future__ import annotations

import time
from dataclasses import dataclass

from linkerbot.hand.hand_protocol_v1 import HandProtocolV1

from . import protocol


@dataclass(frozen=True, slots=True)
class O30iCommunicationErrors:
    latest_index: int
    history: bytes
    timestamp: float


class DiagnosticsManager:
    """Read the normal ``0x4F`` object without confusing it with error replies."""

    def __init__(self, client: HandProtocolV1) -> None:
        self._client = client

    def get_communication_errors(
        self, *, timeout_ms: float = 1000
    ) -> O30iCommunicationErrors:
        payload = self._client.read(
            main_index=protocol.O30I_MI_COMMUNICATION_ERROR,
            length=protocol.O30I_COMMUNICATION_ERROR_BYTE_LENGTH,
            timeout_ms=timeout_ms,
        )
        return O30iCommunicationErrors(
            latest_index=payload[0],
            history=bytes(payload[1:]),
            timestamp=time.time(),
        )
