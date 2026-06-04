"""Fault status sensing for L30."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from linkerbot.exceptions import ValidationError
from linkerbot.relay import DataRelay

from . import protocol
from .client import L30Client

L30_FAULT_VOLTAGE_BIT = 0
L30_FAULT_MAGNETIC_ENCODER_BIT = 1
L30_FAULT_TEMPERATURE_BIT = 2
L30_FAULT_CURRENT_BIT = 3
L30_FAULT_LOAD_BIT = 5


@dataclass(frozen=True, slots=True)
class FaultData:
    """Immutable L30 per-joint fault status data.

    Attributes:
        faults: 17 raw fault bytes in J1..J17 order. Each bit represents a
            documented fault category for that joint.
        timestamp: Unix timestamp when the data was received or decoded.
    """

    faults: tuple[int, ...]
    timestamp: float

    def has_voltage_fault(self, joint_index: int) -> bool:
        """Return whether the joint has a voltage fault bit set.

        Args:
            joint_index: Zero-based joint index.

        Returns:
            True if the voltage fault bit is set for the joint.
        """
        return self._has_bit(joint_index, L30_FAULT_VOLTAGE_BIT)

    def has_magnetic_encoder_fault(self, joint_index: int) -> bool:
        """Return whether the joint has a magnetic encoder fault bit set.

        Args:
            joint_index: Zero-based joint index.

        Returns:
            True if the magnetic encoder fault bit is set for the joint.
        """
        return self._has_bit(joint_index, L30_FAULT_MAGNETIC_ENCODER_BIT)

    def has_temperature_fault(self, joint_index: int) -> bool:
        """Return whether the joint has a temperature fault bit set.

        Args:
            joint_index: Zero-based joint index.

        Returns:
            True if the temperature fault bit is set for the joint.
        """
        return self._has_bit(joint_index, L30_FAULT_TEMPERATURE_BIT)

    def has_current_fault(self, joint_index: int) -> bool:
        """Return whether the joint has a current fault bit set.

        Args:
            joint_index: Zero-based joint index.

        Returns:
            True if the current fault bit is set for the joint.
        """
        return self._has_bit(joint_index, L30_FAULT_CURRENT_BIT)

    def has_load_fault(self, joint_index: int) -> bool:
        """Return whether the joint has a load fault bit set.

        Args:
            joint_index: Zero-based joint index.

        Returns:
            True if the load fault bit is set for the joint.
        """
        return self._has_bit(joint_index, L30_FAULT_LOAD_BIT)

    def _has_bit(self, joint_index: int, bit: int) -> bool:
        return bool(self.faults[joint_index] & (1 << bit))


class FaultManager:
    """Manager for L30 fault status queries and periodic reports."""

    def __init__(self, client: L30Client) -> None:
        """Initialize the fault manager.

        Args:
            client: L30 protocol client used for query and report data.
        """
        self._client = client
        self._relay = DataRelay[FaultData]()
        self._client.add_report_handler(
            protocol.L30_SUBCMD_FAULT, self._on_periodic_report
        )

    def get_blocking(self, timeout_ms: float = 100) -> FaultData:
        """Read fault status bytes and update the cached snapshot.

        Args:
            timeout_ms: Time to wait for the query response.

        Returns:
            FaultData decoded from the L30 query response.

        Raises:
            ValidationError: If timeout_ms is not positive.
            TimeoutError: If no matching response is received before the timeout.
            ProtocolError: If the response status or payload shape is invalid.
        """
        if timeout_ms <= 0:
            raise ValidationError("timeout_ms must be positive")
        response = self._client.read(
            parent=protocol.L30_PARENT_QUERY,
            subcmd=protocol.L30_SUBCMD_FAULT,
            timeout_ms=timeout_ms,
        )
        data = FaultData(
            faults=protocol.decode_u8_response(response), timestamp=time.time()
        )
        self._relay.push(data)
        return data

    def get_snapshot(self) -> FaultData | None:
        """Return the latest cached fault data without sending a request.

        Returns:
            Cached FaultData, or None if no fault data has been received yet.
        """
        return self._relay.snapshot()

    def _send_sense_request(self) -> None:
        self.get_blocking(timeout_ms=100)

    def _set_event_sink(self, sink: Callable[[FaultData], None]) -> None:
        self._relay.set_sink(sink)

    def close(self) -> None:
        """Unregister the periodic fault report handler."""
        self._client.remove_report_handler(
            protocol.L30_SUBCMD_FAULT, self._on_periodic_report
        )

    def _on_periodic_report(self, payload: bytes) -> None:
        self._relay.push(
            FaultData(
                faults=protocol.decode_periodic_u8_report(
                    payload, joint_mask=protocol.L30_PERIODIC_ALL_JOINTS_MASK
                ),
                timestamp=time.time(),
            )
        )
