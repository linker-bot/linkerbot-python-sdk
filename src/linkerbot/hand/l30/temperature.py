"""Temperature sensing for L30."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from linkerbot.exceptions import ValidationError
from linkerbot.relay import DataRelay

from . import protocol
from .client import L30Client


@dataclass(frozen=True, slots=True)
class TemperatureData:
    """Immutable L30 temperature sensor data.

    Attributes:
        temperatures: 17 temperature values in J1..J17 order.
        timestamp: Unix timestamp when the data was received or decoded.
    """

    temperatures: tuple[int, ...]
    timestamp: float


class TemperatureManager:
    """Manager for L30 temperature sensor queries and periodic reports."""

    def __init__(self, client: L30Client) -> None:
        """Initialize the temperature manager.

        Args:
            client: L30 protocol client used for query and report data.
        """
        self._client = client
        self._relay = DataRelay[TemperatureData]()
        self._client.add_report_handler(
            protocol.L30_SUBCMD_TEMPERATURE, self._on_periodic_report
        )

    def get_blocking(self, timeout_ms: float = 100) -> TemperatureData:
        """Read temperature sensor values and update the cached snapshot.

        Args:
            timeout_ms: Time to wait for the query response.

        Returns:
            TemperatureData decoded from the L30 query response.

        Raises:
            ValidationError: If timeout_ms is not positive.
            TimeoutError: If no matching response is received before the timeout.
            ProtocolError: If the response status or payload shape is invalid.
        """
        if timeout_ms <= 0:
            raise ValidationError("timeout_ms must be positive")
        response = self._client.read(
            parent=protocol.L30_PARENT_QUERY,
            subcmd=protocol.L30_SUBCMD_TEMPERATURE,
            timeout_ms=timeout_ms,
        )
        data = TemperatureData(
            temperatures=protocol.decode_u8_response(response), timestamp=time.time()
        )
        self._relay.push(data)
        return data

    def get_snapshot(self) -> TemperatureData | None:
        """Return the latest cached temperature data without sending a request.

        Returns:
            Cached TemperatureData, or None if no temperature data has been
            received yet.
        """
        return self._relay.snapshot()

    def _send_sense_request(self) -> None:
        self.get_blocking(timeout_ms=100)

    def _set_event_sink(self, sink: Callable[[TemperatureData], None]) -> None:
        self._relay.set_sink(sink)

    def close(self) -> None:
        """Unregister the periodic temperature report handler."""
        self._client.remove_report_handler(
            protocol.L30_SUBCMD_TEMPERATURE, self._on_periodic_report
        )

    def _on_periodic_report(self, payload: bytes) -> None:
        self._relay.push(
            TemperatureData(
                temperatures=protocol.decode_periodic_u8_report(
                    payload, joint_mask=protocol.L30_PERIODIC_ALL_JOINTS_MASK
                ),
                timestamp=time.time(),
            )
        )
