"""Torque-byte control and sensing for O30i."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from linkerbot.hand.hand_protocol_v1 import HandProtocolV1
from linkerbot.relay import DataRelay

from . import protocol
from ._runtime import read_vector, write_vector
from .joints import validate_u8_values


@dataclass(frozen=True, slots=True)
class O30iTorqueData:
    torques: tuple[int, ...]
    timestamp: float


class TorqueManager:
    """Read and write the measured one-byte torque object ``0x06``."""

    def __init__(self, client: HandProtocolV1) -> None:
        self._client = client
        self._relay = DataRelay[O30iTorqueData]()

    def set_torques(
        self,
        values: list[int] | tuple[int, ...],
        *,
        timeout_ms: float = 100,
    ) -> None:
        normalized = validate_u8_values(values, name="torques")
        write_vector(
            self._client,
            main_index=protocol.O30I_MI_TORQUE,
            values=normalized,
            timeout_ms=timeout_ms,
        )

    def set_all(self, value: int, *, timeout_ms: float = 100) -> None:
        self.set_torques(
            [value] * protocol.O30I_CONTROLLED_JOINT_COUNT,
            timeout_ms=timeout_ms,
        )

    def get_blocking(self, timeout_ms: float = 100) -> O30iTorqueData:
        data = O30iTorqueData(
            torques=read_vector(
                self._client,
                main_index=protocol.O30I_MI_TORQUE,
                timeout_ms=timeout_ms,
            ),
            timestamp=time.time(),
        )
        self._relay.push(data)
        return data

    def get_snapshot(self) -> O30iTorqueData | None:
        return self._relay.snapshot()

    def _send_sense_request(self) -> None:
        self.get_blocking(timeout_ms=100)

    def _set_event_sink(self, sink: Callable[[O30iTorqueData], None]) -> None:
        self._relay.set_sink(sink)

    def close(self) -> None:
        """Release manager resources; this manager owns no threads."""
