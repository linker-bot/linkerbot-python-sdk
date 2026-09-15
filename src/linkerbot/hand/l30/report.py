"""Periodic report configuration for L30."""

from __future__ import annotations

from enum import Enum

from linkerbot.exceptions import ValidationError

from . import protocol
from .client import L30Client


class ReportSource(str, Enum):
    """L30 sensor sources that support device-side periodic reports."""

    ANGLE = "angle"
    CURRENT = "current"
    SPEED = "speed"
    TEMPERATURE = "temperature"
    FAULT = "fault"


_REPORT_SUBCOMMANDS = {
    ReportSource.ANGLE: protocol.L30_SUBCMD_POSITION,
    ReportSource.CURRENT: protocol.L30_SUBCMD_CURRENT,
    ReportSource.SPEED: protocol.L30_SUBCMD_SPEED,
    ReportSource.TEMPERATURE: protocol.L30_SUBCMD_TEMPERATURE,
    ReportSource.FAULT: protocol.L30_SUBCMD_FAULT,
}


class ReportManager:
    """Manager for L30 device-side periodic report configuration.

    Periodic reports are sent by the device without a host query and are routed
    into the same manager snapshots and unified stream events as blocking reads.
    """

    def __init__(self, client: L30Client) -> None:
        """Initialize the report manager.

        Args:
            client: L30 protocol client used to send periodic report commands.
        """
        self._client = client
        self._enabled_sources: set[ReportSource] = set()

    def configure(
        self,
        source: ReportSource,
        *,
        enabled: bool = True,
        period_ms: int = protocol.L30_PERIODIC_MIN_PERIOD_MS,
        joint_mask: int = protocol.L30_PERIODIC_ALL_JOINTS_MASK,
        timeout_ms: float = 100,
    ) -> None:
        """Configure one periodic report source.

        Args:
            source: Sensor source to configure.
            enabled: Whether to enable or disable periodic reports.
            period_ms: Report period in milliseconds, between 20 and 600000.
            joint_mask: Bit mask selecting joints. A mask of 0 follows the L30
                protocol convention for all joints.
            timeout_ms: Time to wait for the configuration ACK.

        Raises:
            ValidationError: If period_ms, joint_mask, or timeout_ms is invalid.
            TimeoutError: If no matching ACK is received before the timeout.
            ProtocolError: If the ACK reports a non-zero status byte.
        """
        if enabled and joint_mask != protocol.L30_PERIODIC_ALL_JOINTS_MASK:
            raise ValidationError(
                "L30 high-level periodic snapshots only support all-joint reports"
            )
        response = self._client.request_ack(
            parent=protocol.L30_PARENT_PERIODIC,
            subcmd=_REPORT_SUBCOMMANDS[source],
            payload=protocol.encode_periodic_config(
                enabled=enabled, period_ms=period_ms, joint_mask=joint_mask
            ),
            timeout_ms=timeout_ms,
            dlc=protocol.L30_PERIODIC_CONFIG_DLC,
        )
        protocol.check_response_status(response)
        if enabled:
            self._enabled_sources.add(source)
        else:
            self._enabled_sources.discard(source)

    def disable(self, source: ReportSource, *, timeout_ms: float = 100) -> None:
        """Disable one periodic report source.

        Args:
            source: Sensor source to disable.
            timeout_ms: Time to wait for the disable ACK.
        """
        self.configure(source, enabled=False, timeout_ms=timeout_ms)

    def disable_all(self, *, timeout_ms: float = 100) -> None:
        """Disable every source enabled through this manager.

        Args:
            timeout_ms: Time to wait for each disable ACK.
        """
        for source in tuple(self._enabled_sources):
            self.disable(source, timeout_ms=timeout_ms)

    def start_default(self, *, timeout_ms: float = 100) -> None:
        """Enable the SDK default periodic report set.

        The current default enables angle reports at the minimum L30 v2 period.

        Args:
            timeout_ms: Time to wait for the configuration ACK.
        """
        self.configure(ReportSource.ANGLE, enabled=True, timeout_ms=timeout_ms)
