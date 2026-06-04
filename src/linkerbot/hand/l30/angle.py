"""Angle control and sensing for L30.

This module handles 17-joint angle target commands, blocking angle queries,
and angle snapshots updated by queries or device-side periodic reports.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from linkerbot.exceptions import ValidationError
from linkerbot.relay import DataRelay

from . import protocol
from .client import L30Client
from .joints import L30Angle


@dataclass(frozen=True, slots=True)
class AngleData:
    """Immutable L30 angle sensor data.

    Attributes:
        angles: Joint angles in L30 raw units, ordered by J1 through J17.
        timestamp: Unix timestamp when the data was received or decoded.
    """

    angles: L30Angle
    timestamp: float


class AngleManager:
    """Manager for L30 joint angle commands and angle sensor data.

    Angle commands are validated against the documented command ranges for each
    joint. Sensor readback can contain calibrated raw values outside those
    command ranges, so blocking reads and periodic reports only require 17
    integer values.
    """

    def __init__(self, client: L30Client) -> None:
        """Initialize the angle manager.

        Args:
            client: L30 protocol client used for control, query, and report data.
        """
        self._client = client
        self._relay = DataRelay[AngleData]()
        self._client.add_report_handler(
            protocol.L30_SUBCMD_POSITION, self._on_periodic_report
        )

    def set_angles(self, angles: L30Angle | list[int] | tuple[int, ...]) -> None:
        """Send 17 target joint angles to the hand.

        Args:
            angles: L30Angle or 17 raw integer target angles in J1..J17 order.

        Raises:
            ValidationError: If the value count, type, or command range is invalid.
        """
        if not isinstance(angles, L30Angle):
            angles = L30Angle.from_list(angles)
        self._client.send_no_ack(
            parent=protocol.L30_PARENT_CONTROL,
            subcmd=protocol.L30_SUBCMD_POSITION,
            payload=protocol.encode_i16_vector(tuple(angles.values)),
            dlc=protocol.L30_VECTOR_DLC,
        )

    def get_blocking(self, timeout_ms: float = 100) -> AngleData:
        """Read current joint angles and update the cached snapshot.

        Args:
            timeout_ms: Time to wait for the query response.

        Returns:
            AngleData decoded from the L30 query response.

        Raises:
            ValidationError: If timeout_ms is not positive.
            TimeoutError: If no matching response is received before the timeout.
            ProtocolError: If the response status or payload shape is invalid.
        """
        if timeout_ms <= 0:
            raise ValidationError("timeout_ms must be positive")
        response = self._client.read(
            parent=protocol.L30_PARENT_QUERY,
            subcmd=protocol.L30_SUBCMD_POSITION,
            timeout_ms=timeout_ms,
        )
        data = AngleData(
            angles=L30Angle.from_sensor_values(
                list(protocol.decode_i16_response(response))
            ),
            timestamp=time.time(),
        )
        self._relay.push(data)
        return data

    def get_snapshot(self) -> AngleData | None:
        """Return the latest cached angle data without sending a request.

        Returns:
            Cached AngleData, or None if no angle data has been received yet.
        """
        return self._relay.snapshot()

    def _send_sense_request(self) -> None:
        self.get_blocking(timeout_ms=100)

    def _set_event_sink(self, sink: Callable[[AngleData], None]) -> None:
        self._relay.set_sink(sink)

    def close(self) -> None:
        """Unregister the periodic angle report handler."""
        self._client.remove_report_handler(
            protocol.L30_SUBCMD_POSITION, self._on_periodic_report
        )

    def _on_periodic_report(self, payload: bytes) -> None:
        values = protocol.decode_periodic_i16_report(
            payload, joint_mask=protocol.L30_PERIODIC_ALL_JOINTS_MASK
        )
        self._relay.push(
            AngleData(
                angles=L30Angle.from_sensor_values(list(values)), timestamp=time.time()
            )
        )
