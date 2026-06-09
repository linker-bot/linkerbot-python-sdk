"""Angle control and sensing for O20.

This module handles 16-joint target angle commands, blocking angle queries,
and angle snapshots updated by host-side reads.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from linkerbot.exceptions import ValidationError
from linkerbot.relay import DataRelay

from . import protocol
from .client import O20Client
from .joints import O20Angle


@dataclass(frozen=True, slots=True)
class O20AngleData:
    """Immutable O20 angle sensor data.

    Attributes:
        angles: 16 joint angles in raw protocol units, ordered by motor ID.
        timestamp: Unix timestamp when the data was decoded.
    """

    angles: O20Angle
    timestamp: float


class AngleManager:
    """Manager for O20 joint angle commands and angle sensor data.

    Angle commands are validated against the documented command ranges for each
    joint. Sensor readback can contain calibrated raw values outside those
    command ranges, so blocking reads only require 16 integer values.
    """

    def __init__(self, client: O20Client) -> None:
        """Initialize the angle manager.

        Args:
            client: O20 protocol client used for register read/write commands.
        """
        self._client = client
        self._relay = DataRelay[O20AngleData]()

    def set_angles(self, angles: O20Angle | list[int] | tuple[int, ...]) -> None:
        """Send 16 target joint angles to the hand.

        Args:
            angles: O20Angle or 16 raw integer target angles in motor-ID order.

        Raises:
            ValidationError: If the value count, type, or command range is invalid.
        """
        if not isinstance(angles, O20Angle):
            angles = O20Angle.from_list(angles)
        self._client.write(
            register=protocol.O20_REG_TARGET_POS,
            payload=protocol.encode_i16_vector(tuple(angles.values)),
            dlc=protocol.O20_VECTOR_DLC,
        )

    def set_percentages(self, values: list[float] | tuple[float, ...]) -> None:
        """Send 16 percentage target angles in motor-ID order.

        Args:
            values: 16 percentage values, each between 0 and 100.

        Raises:
            ValidationError: If the value count, type, or percentage range is invalid.
        """
        from .joints import percentages_to_raw

        self.set_angles(percentages_to_raw(values))

    def get_blocking(self, timeout_ms: float = 100) -> O20AngleData:
        """Read current joint angles and update the cached snapshot.

        Args:
            timeout_ms: Time to wait for the read response.

        Returns:
            O20AngleData decoded from the register response.

        Raises:
            ValidationError: If timeout_ms is not positive.
            TimeoutError: If no matching response arrives before the timeout.
            ProtocolError: If the response payload is shorter than expected.
        """
        if timeout_ms <= 0:
            raise ValidationError("timeout_ms must be positive")
        response = self._client.read(
            register=protocol.O20_REG_CURRENT_POS, timeout_ms=timeout_ms
        )
        data = O20AngleData(
            angles=O20Angle.from_sensor_values(
                list(protocol.decode_i16_vector_response(response))
            ),
            timestamp=time.time(),
        )
        self._relay.push(data)
        return data

    def get_snapshot(self) -> O20AngleData | None:
        """Return the latest cached angle data without sending a request.

        Returns:
            Cached O20AngleData, or None if no angle data has been received yet.
        """
        return self._relay.snapshot()

    def _send_sense_request(self) -> None:
        self.get_blocking(timeout_ms=100)

    def _set_event_sink(self, sink: Callable[[O20AngleData], None]) -> None:
        self._relay.set_sink(sink)

    def close(self) -> None:
        """Release any per-manager resources. The angle manager has none."""
