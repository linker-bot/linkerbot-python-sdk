"""Per-slot motion-time control for O30 (10 ms per protocol tick)."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from linkerbot.exceptions import ValidationError
from linkerbot.hand.hand_protocol_v1 import HandProtocolV1
from linkerbot.relay import DataRelay

from . import protocol
from ._runtime import read_vector, write_vector
from .joints import validate_u8_values

O30_MOTION_TIME_TICK_MS = 10


@dataclass(frozen=True, slots=True)
class O30MotionTimeData:
    ticks: tuple[int, ...]
    timestamp: float

    @property
    def milliseconds(self) -> tuple[int, ...]:
        """Return every tick value converted to milliseconds."""
        return tuple(value * O30_MOTION_TIME_TICK_MS for value in self.ticks)


class MotionTimeManager:
    """Read and write motion-time object ``0x08``."""

    def __init__(self, client: HandProtocolV1) -> None:
        self._client = client
        self._relay = DataRelay[O30MotionTimeData]()

    def set_ticks(
        self,
        values: list[int] | tuple[int, ...],
        *,
        timeout_ms: float = 100,
    ) -> None:
        normalized = validate_u8_values(values, name="motion_time_ticks")
        write_vector(
            self._client,
            main_index=protocol.O30_MI_MOTION_TIME,
            values=normalized,
            timeout_ms=timeout_ms,
        )

    def set_all_ticks(self, value: int, *, timeout_ms: float = 100) -> None:
        self.set_ticks(
            [value] * protocol.O30_CONTROLLED_JOINT_COUNT,
            timeout_ms=timeout_ms,
        )

    def set_milliseconds(
        self,
        values: list[int] | tuple[int, ...],
        *,
        timeout_ms: float = 100,
    ) -> None:
        """Set durations that are exact multiples of 10 ms, up to 2550 ms."""
        normalized = tuple(values)
        if len(normalized) != protocol.O30_CONTROLLED_JOINT_COUNT:
            raise ValidationError(
                "motion_time_ms must contain "
                f"{protocol.O30_CONTROLLED_JOINT_COUNT} values"
            )
        ticks: list[int] = []
        for index, value in enumerate(normalized):
            protocol._validate_int(value, f"motion_time_ms[{index}]")
            if value < 0 or value > 2550 or value % O30_MOTION_TIME_TICK_MS:
                raise ValidationError(
                    f"motion_time_ms[{index}] must be a multiple of 10 "
                    "between 0 and 2550"
                )
            ticks.append(value // O30_MOTION_TIME_TICK_MS)
        self.set_ticks(ticks, timeout_ms=timeout_ms)

    def get_blocking(self, timeout_ms: float = 100) -> O30MotionTimeData:
        data = O30MotionTimeData(
            ticks=read_vector(
                self._client,
                main_index=protocol.O30_MI_MOTION_TIME,
                timeout_ms=timeout_ms,
            ),
            timestamp=time.time(),
        )
        self._relay.push(data)
        return data

    def get_snapshot(self) -> O30MotionTimeData | None:
        return self._relay.snapshot()

    def _send_sense_request(self) -> None:
        self.get_blocking(timeout_ms=100)

    def _set_event_sink(self, sink: Callable[[O30MotionTimeData], None]) -> None:
        self._relay.set_sink(sink)

    def close(self) -> None:
        """Release manager resources; this manager owns no threads."""


# Backward-compatible aliases for the former model name.
O30iMotionTimeData = O30MotionTimeData
