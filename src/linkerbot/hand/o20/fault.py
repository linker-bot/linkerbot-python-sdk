"""Per-motor fault status sensing for O20.

Each motor reports one fault byte. The values follow the protocol spec:

* 0 — no fault
* 1 — over temperature
* 2 — over current
* 3 — communication error
* 4 — motor not calibrated

A clear command writes 0 to every motor's error status byte. This is a
non-persistent recovery action that asks the motor controller to drop a latched
fault state; it is the only write to register 0x02 exposed by this SDK.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from linkerbot.exceptions import ValidationError
from linkerbot.relay import DataRelay

from . import protocol
from .client import O20Client
from .joints import O20_JOINT_COUNT


@dataclass(frozen=True, slots=True)
class O20FaultData:
    """Immutable O20 per-motor fault status data.

    Attributes:
        faults: 16 raw fault bytes in motor-ID order. See the module docstring
            for the documented values.
        timestamp: Unix timestamp when the data was decoded.
    """

    faults: tuple[int, ...]
    timestamp: float

    def has_fault(self, motor_index: int) -> bool:
        """Return whether the motor reports any fault.

        Args:
            motor_index: Zero-based motor index in the 0..15 range.

        Returns:
            True if the motor's fault byte is non-zero.
        """
        return self.faults[motor_index] != protocol.O20_FAULT_NONE

    def fault_message(self, motor_index: int) -> str:
        """Return a readable message for the motor's fault byte.

        Args:
            motor_index: Zero-based motor index in the 0..15 range.

        Returns:
            Documented fault message, or ``"unknown fault"`` for unknown bytes.
        """
        return protocol.fault_message(self.faults[motor_index])


class FaultManager:
    """Manager for O20 per-motor fault status reads and clears."""

    def __init__(self, client: O20Client) -> None:
        """Initialize the fault manager.

        Args:
            client: O20 protocol client used for register read/write commands.
        """
        self._client = client
        self._relay = DataRelay[O20FaultData]()

    def get_blocking(self, timeout_ms: float = 100) -> O20FaultData:
        """Read per-motor fault bytes and update the cached snapshot.

        Args:
            timeout_ms: Time to wait for the read response.

        Returns:
            O20FaultData decoded from the register response.

        Raises:
            ValidationError: If timeout_ms is not positive.
            TimeoutError: If no matching response arrives before the timeout.
            ProtocolError: If the response payload is shorter than expected.
        """
        if timeout_ms <= 0:
            raise ValidationError("timeout_ms must be positive")
        response = self._client.read(
            register=protocol.O20_REG_ERROR_STATUS, timeout_ms=timeout_ms
        )
        data = O20FaultData(
            faults=protocol.decode_u8_vector_response(response),
            timestamp=time.time(),
        )
        self._relay.push(data)
        return data

    def clear(self) -> None:
        """Send a clear-fault command to every motor.

        Writes a zero byte to each motor's error status slot. The hand may use
        this to drop latched fault states; persistence is not guaranteed by
        the SDK.
        """
        self._client.write(
            register=protocol.O20_REG_ERROR_STATUS,
            payload=protocol.encode_u8_vector([0] * O20_JOINT_COUNT),
            dlc=protocol.O20_U8_VECTOR_DLC,
        )

    def get_snapshot(self) -> O20FaultData | None:
        """Return the latest cached fault data without sending a request."""
        return self._relay.snapshot()

    def _send_sense_request(self) -> None:
        self.get_blocking(timeout_ms=100)

    def _set_event_sink(self, sink: Callable[[O20FaultData], None]) -> None:
        self._relay.set_sink(sink)

    def close(self) -> None:
        """Release any per-manager resources. The fault manager has none."""
