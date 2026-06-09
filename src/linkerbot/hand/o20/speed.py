"""Speed control and sensing for O20.

This module sends 16-joint speed targets and reads measured speed values.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from linkerbot.exceptions import ValidationError
from linkerbot.relay import DataRelay

from . import protocol
from .client import O20Client
from .joints import O20_JOINT_COUNT, validate_int_values

O20_SPEED_MIN = 0
O20_SPEED_MAX = 100


@dataclass(frozen=True, slots=True)
class O20SpeedData:
    """Immutable O20 speed data.

    Attributes:
        speeds: 16 speed values in motor-ID order.
        timestamp: Unix timestamp when the data was decoded.
    """

    speeds: tuple[int, ...]
    timestamp: float


class SpeedManager:
    """Manager for O20 speed targets and measured speeds.

    Speed targets use the documented O20 range of 0 through 100 for every
    joint. Measured readback is decoded as a 17-slot signed 16-bit register
    response with the trailing reserved slot dropped.
    """

    def __init__(self, client: O20Client) -> None:
        """Initialize the speed manager.

        Args:
            client: O20 protocol client used for register read/write commands.
        """
        self._client = client
        self._relay = DataRelay[O20SpeedData]()

    def set_speeds(self, speeds: list[int] | tuple[int, ...]) -> None:
        """Send per-joint speed targets.

        Args:
            speeds: 16 integer speed values in motor-ID order. Each value must
                be between 0 and 100.

        Raises:
            ValidationError: If the count, type, or speed range is invalid.
        """
        values = validate_int_values(
            speeds, name="speeds", minimum=O20_SPEED_MIN, maximum=O20_SPEED_MAX
        )
        self._client.write(
            register=protocol.O20_REG_TARGET_VEL,
            payload=protocol.encode_i16_vector(values),
            dlc=protocol.O20_VECTOR_DLC,
        )

    def set_all(self, speed: int) -> None:
        """Send the same speed target to all 16 joints.

        Args:
            speed: Speed value applied to every joint, between 0 and 100.

        Raises:
            ValidationError: If speed is outside the documented range.
        """
        self.set_speeds([speed] * O20_JOINT_COUNT)

    def get_blocking(self, timeout_ms: float = 100) -> O20SpeedData:
        """Read current measured speeds and update the cached snapshot.

        Args:
            timeout_ms: Time to wait for the read response.

        Returns:
            O20SpeedData decoded from the register response.

        Raises:
            ValidationError: If timeout_ms is not positive.
            TimeoutError: If no matching response arrives before the timeout.
            ProtocolError: If the response payload is shorter than expected.
        """
        if timeout_ms <= 0:
            raise ValidationError("timeout_ms must be positive")
        response = self._client.read(
            register=protocol.O20_REG_CURRENT_VEL, timeout_ms=timeout_ms
        )
        data = O20SpeedData(
            speeds=protocol.decode_i16_vector_response(response),
            timestamp=time.time(),
        )
        self._relay.push(data)
        return data

    def get_snapshot(self) -> O20SpeedData | None:
        """Return the latest cached speed data without sending a request."""
        return self._relay.snapshot()

    def _send_sense_request(self) -> None:
        self.get_blocking(timeout_ms=100)

    def _set_event_sink(self, sink: Callable[[O20SpeedData], None]) -> None:
        self._relay.set_sink(sink)

    def close(self) -> None:
        """Release any per-manager resources. The speed manager has none."""
