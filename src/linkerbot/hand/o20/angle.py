"""Angle control and sensing for O20.

The public API is aligned with :mod:`linkerbot.hand.l6.angle` and
:mod:`linkerbot.hand.l30.angle`: ``set_angles`` takes 0-100 percentage values
and ``set_raw_angles`` takes protocol-native raw integers. Sensor readback
(``get_blocking``) returns ``O20Angle`` in percentage space; call
:meth:`O20Angle.to_raw` if you need the underlying protocol values.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from linkerbot.exceptions import ValidationError
from linkerbot.relay import DataRelay

from . import protocol
from .client import O20Client
from .joints import O20Angle, validate_raw_command_values


@dataclass(frozen=True, slots=True)
class O20AngleData:
    """Immutable O20 angle sensor data.

    Attributes:
        angles: Joint angles as 0-100 float percentages in motor-ID order.
            Values may occasionally lie slightly outside [0, 100] when the
            hardware calibrates or overshoots the documented command range.
        timestamp: Unix timestamp when the data was decoded.
    """

    angles: O20Angle
    timestamp: float


class AngleManager:
    """Manager for O20 joint angle commands and angle sensor data.

    ``set_angles`` accepts 0-100 percentage values (aligned with L6 and L30).
    Use ``set_raw_angles`` when you need to command the exact protocol
    integers from :data:`O20_JOINT_SPECS`. Sensor readback returns
    percentages via :class:`O20AngleData`.
    """

    def __init__(self, client: O20Client) -> None:
        """Initialize the angle manager.

        Args:
            client: O20 protocol client used for register read/write commands.
        """
        self._client = client
        self._relay = DataRelay[O20AngleData]()

    def set_angles(self, angles: O20Angle | list[float] | tuple[float, ...]) -> None:
        """Send 16 target joint angles as 0-100 percentages.

        This is the L6/L30-aligned high-level API: pass a list of 16 floats
        between 0 and 100 (0 % = ``spec.minimum``, 100 % = ``spec.maximum``
        for each joint). The manager converts to raw integers using each
        joint's spec range before transmission.

        Args:
            angles: :class:`O20Angle` or 16-element sequence of 0-100 floats
                in motor-ID order.

        Raises:
            ValidationError: If the value count, type, or 0-100 range is invalid.
        """
        if isinstance(angles, O20Angle):
            raw_values = angles.to_raw()
        elif isinstance(angles, (list, tuple)):
            raw_values = O20Angle.from_list(angles).to_raw()
        else:
            raise ValidationError(
                f"Expected O20Angle or list/tuple of floats, "
                f"got {type(angles).__name__}"
            )
        self._send_raw_angles(raw_values)

    def set_raw_angles(self, raw_angles: list[int] | tuple[int, ...]) -> None:
        """Send 16 target joint angles as raw protocol integers.

        Each value must lie in its joint's documented
        ``[spec.minimum, spec.maximum]`` range (see :data:`O20_JOINT_SPECS`).

        Args:
            raw_angles: 16-element sequence of ints in motor-ID order.

        Raises:
            ValidationError: If count, type, or per-joint spec range is invalid.
        """
        validated = validate_raw_command_values(raw_angles)
        self._send_raw_angles(list(validated))

    def get_blocking(self, timeout_ms: float = 100) -> O20AngleData:
        """Read current joint angles and update the cached snapshot.

        Args:
            timeout_ms: Time to wait for the read response.

        Returns:
            O20AngleData whose ``angles`` are 0-100 percentages (may slightly
            exceed the range on hardware calibration overshoot).

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
            angles=O20Angle.from_sensor_raw(
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

    def _send_raw_angles(self, raw_values: list[int]) -> None:
        self._client.write(
            register=protocol.O20_REG_TARGET_POS,
            payload=protocol.encode_i16_vector(tuple(raw_values)),
            dlc=protocol.O20_VECTOR_DLC,
        )

    def _send_sense_request(self) -> None:
        self.get_blocking(timeout_ms=100)

    def _set_event_sink(self, sink: Callable[[O20AngleData], None]) -> None:
        self._relay.set_sink(sink)

    def close(self) -> None:
        """Release any per-manager resources. The angle manager has none."""
