"""Current sensing for O20."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from linkerbot.exceptions import ValidationError
from linkerbot.relay import DataRelay

from . import protocol
from .client import O20Client


@dataclass(frozen=True, slots=True)
class O20CurrentData:
    """Immutable O20 motor current sensor data.

    Attributes:
        currents: 16 motor current values in motor-ID order, in mA.
        timestamp: Unix timestamp when the data was decoded.
    """

    currents: tuple[int, ...]
    timestamp: float


class CurrentManager:
    """Manager for O20 motor current reads."""

    def __init__(self, client: O20Client) -> None:
        """Initialize the current manager.

        Args:
            client: O20 protocol client used for register read commands.
        """
        self._client = client
        self._relay = DataRelay[O20CurrentData]()

    def get_blocking(self, timeout_ms: float = 100) -> O20CurrentData:
        """Read motor currents and update the cached snapshot.

        Args:
            timeout_ms: Time to wait for the read response.

        Returns:
            O20CurrentData decoded from the register response.

        Raises:
            ValidationError: If timeout_ms is not positive.
            TimeoutError: If no matching response arrives before the timeout.
            ProtocolError: If the response payload is shorter than expected.
        """
        if timeout_ms <= 0:
            raise ValidationError("timeout_ms must be positive")
        response = self._client.read(
            register=protocol.O20_REG_MOTOR_CURRENT, timeout_ms=timeout_ms
        )
        data = O20CurrentData(
            currents=protocol.decode_i16_vector_response(response),
            timestamp=time.time(),
        )
        self._relay.push(data)
        return data

    def get_snapshot(self) -> O20CurrentData | None:
        """Return the latest cached current data without sending a request."""
        return self._relay.snapshot()

    def _send_sense_request(self) -> None:
        self.get_blocking(timeout_ms=100)

    def _set_event_sink(self, sink: Callable[[O20CurrentData], None]) -> None:
        self._relay.set_sink(sink)

    def close(self) -> None:
        """Release any per-manager resources. The current manager has none."""
