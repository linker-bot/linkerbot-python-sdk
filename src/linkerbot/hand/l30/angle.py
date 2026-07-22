"""Angle control and sensing for L30.

The public API is aligned with :mod:`linkerbot.hand.l6.angle`: ``set_angles``
takes 0-100 percentage values and ``set_raw_angles`` takes protocol-native
raw integers. Sensor readback (``get_blocking`` / periodic reports) returns
``L30Angle`` in percentage space; call :meth:`L30Angle.to_raw` if you need
the underlying protocol values.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from linkerbot.exceptions import ValidationError
from linkerbot.relay import DataRelay

from . import protocol
from .client import L30Client
from .joints import L30Angle, validate_raw_command_values


@dataclass(frozen=True, slots=True)
class AngleData:
    """Immutable L30 angle sensor data.

    Attributes:
        angles: Joint angles as 0-100 float percentages in J1..J17 order.
            Values may occasionally lie slightly outside [0, 100] when the
            hardware calibrates or overshoots the documented command range.
        timestamp: Unix timestamp when the data was received or decoded.
    """

    angles: L30Angle
    timestamp: float


class AngleManager:
    """Manager for L30 joint angle commands and angle sensor data.

    ``set_angles`` accepts 0-100 percentage values (aligned with the L6 API).
    Use ``set_raw_angles`` when you need to command the exact protocol
    integers from :data:`L30_JOINT_SPECS`. Sensor readback returns
    percentages via :class:`AngleData`.
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

    def set_angles(self, angles: L30Angle | Sequence[int | float]) -> None:
        """Send 17 target joint angles as 0-100 percentages.

        This is the L6-aligned high-level API: pass a list of 17 floats
        between 0 and 100 (0 % = ``spec.minimum``, 100 % = ``spec.maximum``
        for each joint). The manager converts to raw integers using each
        joint's spec range before transmission.

        Args:
            angles: :class:`L30Angle` or 17-element sequence of 0-100 numbers
                in J1..J17 order.

        Raises:
            ValidationError: If the value count, type, or 0-100 range is invalid.
        """
        if isinstance(angles, L30Angle):
            raw_values = angles.to_raw()
        elif isinstance(angles, Sequence):
            raw_values = L30Angle.from_list(angles).to_raw()
        else:
            raise ValidationError(
                f"Expected L30Angle or a sequence of numbers, "
                f"got {type(angles).__name__}"
            )
        self._send_raw_angles(raw_values)

    def set_raw_angles(self, raw_angles: list[int] | tuple[int, ...]) -> None:
        """Send 17 target joint angles as raw protocol integers.

        Each value must lie in its joint's documented
        ``[spec.minimum, spec.maximum]`` range (see :data:`L30_JOINT_SPECS`).

        Args:
            raw_angles: 17-element sequence of ints in J1..J17 order.

        Raises:
            ValidationError: If count, type, or per-joint spec range is invalid.
        """
        validated = validate_raw_command_values(raw_angles)
        self._send_raw_angles(list(validated))

    def get_blocking(self, timeout_ms: float = 100) -> AngleData:
        """Read current joint angles and update the cached snapshot.

        Args:
            timeout_ms: Time to wait for the query response.

        Returns:
            AngleData whose ``angles`` are 0-100 percentages (may slightly
            exceed the range on hardware calibration overshoot).

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
            angles=L30Angle.from_sensor_raw(
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

    def _send_raw_angles(self, raw_values: list[int]) -> None:
        self._client.send_no_ack(
            parent=protocol.L30_PARENT_CONTROL,
            subcmd=protocol.L30_SUBCMD_POSITION,
            payload=protocol.encode_i16_vector(tuple(raw_values)),
            dlc=protocol.L30_VECTOR_DLC,
        )

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
                angles=L30Angle.from_sensor_raw(list(values)),
                timestamp=time.time(),
            )
        )
