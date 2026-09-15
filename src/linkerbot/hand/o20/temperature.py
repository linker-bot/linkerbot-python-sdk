"""Temperature sensing for O20."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from linkerbot.exceptions import ValidationError
from linkerbot.relay import DataRelay

from . import protocol
from .client import O20Client


@dataclass(frozen=True, slots=True)
class O20TemperatureData:
    """Immutable O20 motor temperature sensor data.

    Attributes:
        temperatures: 16 temperature values in motor-ID order, one per motor.
        timestamp: Unix timestamp when the data was decoded.
    """

    temperatures: tuple[int, ...]
    timestamp: float


class TemperatureManager:
    """Manager for O20 motor temperature reads."""

    def __init__(self, client: O20Client) -> None:
        """Initialize the temperature manager.

        Args:
            client: O20 protocol client used for register read commands.
        """
        self._client = client
        self._relay = DataRelay[O20TemperatureData]()

    def get_blocking(self, timeout_ms: float = 100) -> O20TemperatureData:
        """Read motor temperatures and update the cached snapshot.

        Args:
            timeout_ms: Time to wait for the read response.

        Returns:
            O20TemperatureData decoded from the register response.

        Raises:
            ValidationError: If timeout_ms is not positive.
            TimeoutError: If no matching response arrives before the timeout.
            ProtocolError: If the response payload is shorter than expected.
        """
        if timeout_ms <= 0:
            raise ValidationError("timeout_ms must be positive")
        response = self._client.read(
            register=protocol.O20_REG_TEMP_DATA, timeout_ms=timeout_ms
        )
        data = O20TemperatureData(
            temperatures=protocol.decode_u8_vector_response(response),
            timestamp=time.time(),
        )
        self._relay.push(data)
        return data

    def get_snapshot(self) -> O20TemperatureData | None:
        """Return the latest cached temperature data without sending a request."""
        return self._relay.snapshot()

    def _send_sense_request(self) -> None:
        self.get_blocking(timeout_ms=100)

    def _set_event_sink(self, sink: Callable[[O20TemperatureData], None]) -> None:
        self._relay.set_sink(sink)

    def close(self) -> None:
        """Release any per-manager resources. The temperature manager has none."""
