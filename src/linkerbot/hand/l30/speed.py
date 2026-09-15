"""Speed control and sensing for L30.

This module sends 17-joint speed targets and reads speed values through blocking
queries or device-side periodic reports.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from linkerbot.exceptions import ValidationError
from linkerbot.relay import DataRelay

from . import protocol
from .client import L30Client
from .joints import L30_JOINT_COUNT, validate_u16_values

L30_SPEED_MIN = 1
L30_SPEED_MAX = 250


@dataclass(frozen=True, slots=True)
class SpeedData:
    """Immutable L30 speed data.

    Attributes:
        speeds: 17 speed values in J1..J17 order.
        timestamp: Unix timestamp when the data was received or decoded.
    """

    speeds: tuple[int, ...]
    timestamp: float


class SpeedManager:
    """Manager for L30 speed targets and speed sensor data.

    Speed commands use unsigned 16-bit payload values and must be within the
    documented L30 range of 1 through 250 for every joint.
    """

    def __init__(self, client: L30Client) -> None:
        """Initialize the speed manager.

        Args:
            client: L30 protocol client used for control, query, and report data.
        """
        self._client = client
        self._relay = DataRelay[SpeedData]()
        self._client.add_report_handler(
            protocol.L30_SUBCMD_SPEED, self._on_periodic_report
        )

    def set_speeds(self, speeds: list[int] | tuple[int, ...]) -> None:
        """Send per-joint speed targets.

        Args:
            speeds: 17 integer speed values in J1..J17 order. Each value must be
                between 1 and 250.

        Raises:
            ValidationError: If the count, type, or speed range is invalid.
        """
        values = validate_u16_values(
            speeds, name="speeds", minimum=L30_SPEED_MIN, maximum=L30_SPEED_MAX
        )
        self._client.send_no_ack(
            parent=protocol.L30_PARENT_CONTROL,
            subcmd=protocol.L30_SUBCMD_SPEED,
            payload=protocol.encode_u16_vector(
                values, minimum=L30_SPEED_MIN, maximum=L30_SPEED_MAX
            ),
            dlc=protocol.L30_VECTOR_DLC,
        )

    def set_all(self, speed: int) -> None:
        """Send the same speed target to all 17 joints.

        Args:
            speed: Speed value applied to every joint, between 1 and 250.

        Raises:
            ValidationError: If speed is outside the documented range.
        """
        self.set_speeds([speed] * L30_JOINT_COUNT)

    def get_blocking(self, timeout_ms: float = 100) -> SpeedData:
        """Read current speed values and update the cached snapshot.

        Args:
            timeout_ms: Time to wait for the query response.

        Returns:
            SpeedData decoded from the L30 query response.

        Raises:
            ValidationError: If timeout_ms is not positive.
            TimeoutError: If no matching response is received before the timeout.
            ProtocolError: If the response status or payload shape is invalid.
        """
        if timeout_ms <= 0:
            raise ValidationError("timeout_ms must be positive")
        response = self._client.read(
            parent=protocol.L30_PARENT_QUERY,
            subcmd=protocol.L30_SUBCMD_SPEED,
            timeout_ms=timeout_ms,
        )
        data = SpeedData(
            speeds=protocol.decode_i16_response(response),
            timestamp=time.time(),
        )
        self._relay.push(data)
        return data

    def get_snapshot(self) -> SpeedData | None:
        """Return the latest cached speed data without sending a request.

        Returns:
            Cached SpeedData, or None if no speed data has been received yet.
        """
        return self._relay.snapshot()

    def _send_sense_request(self) -> None:
        self.get_blocking(timeout_ms=100)

    def _set_event_sink(self, sink: Callable[[SpeedData], None]) -> None:
        self._relay.set_sink(sink)

    def close(self) -> None:
        """Unregister the periodic speed report handler."""
        self._client.remove_report_handler(
            protocol.L30_SUBCMD_SPEED, self._on_periodic_report
        )

    def _on_periodic_report(self, payload: bytes) -> None:
        self._relay.push(
            SpeedData(
                speeds=protocol.decode_periodic_i16_report(
                    payload, joint_mask=protocol.L30_PERIODIC_ALL_JOINTS_MASK
                ),
                timestamp=time.time(),
            )
        )
