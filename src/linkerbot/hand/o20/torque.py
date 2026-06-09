"""Torque target control for O20."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from linkerbot.relay import DataRelay

from . import protocol
from .client import O20Client
from .joints import O20_JOINT_COUNT, validate_int_values

O20_TORQUE_MIN = 0
O20_TORQUE_MAX = 1000


@dataclass(frozen=True, slots=True)
class O20TorqueData:
    """Immutable O20 target torque data.

    Attributes:
        torques: 16 commanded torque targets in motor-ID order.
        timestamp: Unix timestamp when the target torque command was sent.
    """

    torques: tuple[int, ...]
    timestamp: float


class TorqueManager:
    """Manager for O20 target torque commands.

    The O20 protocol exposes torque as a control target in this SDK. The cached
    snapshot stores the last successfully encoded target command; it is not a
    measured torque sensor readback.
    """

    def __init__(self, client: O20Client) -> None:
        """Initialize the torque manager.

        Args:
            client: O20 protocol client used to send register write commands.
        """
        self._client = client
        self._relay = DataRelay[O20TorqueData]()

    def set_torques(self, torques: list[int] | tuple[int, ...]) -> None:
        """Send per-joint torque targets.

        Args:
            torques: 16 integer torque target values in motor-ID order. Each
                value must be between 0 and 1000 (unit 6.5mA per documentation).

        Raises:
            ValidationError: If the count, type, or torque range is invalid.
        """
        values = validate_int_values(
            torques, name="torques", minimum=O20_TORQUE_MIN, maximum=O20_TORQUE_MAX
        )
        self._client.write(
            register=protocol.O20_REG_TARGET_TORQUE,
            payload=protocol.encode_u16_vector(
                values, minimum=O20_TORQUE_MIN, maximum=O20_TORQUE_MAX
            ),
            dlc=protocol.O20_VECTOR_DLC,
        )
        self._relay.push(O20TorqueData(torques=values, timestamp=time.time()))

    def set_all(self, torque: int) -> None:
        """Send the same torque target to all 16 joints.

        Args:
            torque: Torque target applied to every joint, between 0 and 1000.

        Raises:
            ValidationError: If torque is outside the documented range.
        """
        self.set_torques([torque] * O20_JOINT_COUNT)

    def get_snapshot(self) -> O20TorqueData | None:
        """Return the latest commanded torque target."""
        return self._relay.snapshot()

    def _set_event_sink(self, sink: Callable[[O20TorqueData], None]) -> None:
        self._relay.set_sink(sink)

    def close(self) -> None:
        """Release any per-manager resources. The torque manager has none."""
