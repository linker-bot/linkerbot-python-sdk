"""Raw per-slot fault-state sensing for O30i."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from linkerbot.exceptions import ValidationError
from linkerbot.hand.hand_protocol_v1 import HandProtocolV1
from linkerbot.relay import DataRelay

from . import protocol
from ._runtime import read_vector


@dataclass(frozen=True, slots=True)
class O30iFaultData:
    faults: tuple[int, ...]
    timestamp: float

    def has_fault(self, joint_index: int) -> bool:
        """Return whether one physical joint's raw fault byte is non-zero."""
        protocol._validate_int(joint_index, "joint_index")
        if joint_index < 0 or joint_index >= protocol.O30I_CONTROLLED_JOINT_COUNT:
            raise ValidationError(
                "joint_index must be between 0 and "
                f"{protocol.O30I_CONTROLLED_JOINT_COUNT - 1}"
            )
        return self.faults[joint_index] != 0


class FaultManager:
    """Read fault object ``0x0D`` without assuming undocumented bit meanings."""

    def __init__(self, client: HandProtocolV1) -> None:
        self._client = client
        self._relay = DataRelay[O30iFaultData]()

    def get_blocking(self, timeout_ms: float = 100) -> O30iFaultData:
        data = O30iFaultData(
            faults=read_vector(
                self._client,
                main_index=protocol.O30I_MI_FAULT,
                timeout_ms=timeout_ms,
            ),
            timestamp=time.time(),
        )
        self._relay.push(data)
        return data

    def get_snapshot(self) -> O30iFaultData | None:
        return self._relay.snapshot()

    def _send_sense_request(self) -> None:
        self.get_blocking(timeout_ms=100)

    def _set_event_sink(self, sink: Callable[[O30iFaultData], None]) -> None:
        self._relay.set_sink(sink)

    def close(self) -> None:
        """Release manager resources; this manager owns no threads."""
