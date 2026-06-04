"""Global enable and disable commands for L30."""

from __future__ import annotations

from . import protocol
from .client import L30Client


class ControlManager:
    """Manager for L30 global motor control commands.

    Enable and disable are L30 v2 write commands that require an ACK response.
    They do not update sensor snapshots; they only change the device control
    state.
    """

    def __init__(self, client: L30Client) -> None:
        """Initialize the control manager.

        Args:
            client: L30 protocol client used to send write commands.
        """
        self._client = client

    def enable(self, timeout_ms: float = 100) -> None:
        """Enable the L30 hand motor control state.

        Args:
            timeout_ms: Time to wait for the L30 v2 write ACK.

        Raises:
            ValidationError: If timeout_ms is invalid.
            TimeoutError: If no matching ACK is received before the timeout.
            ProtocolError: If the ACK reports a non-zero status byte.
        """
        response = self._client.request_ack(
            parent=protocol.L30_PARENT_CONTROL,
            subcmd=protocol.L30_SUBCMD_ENABLE,
            payload=protocol.empty_request_payload(),
            timeout_ms=timeout_ms,
            dlc=protocol.L30_EMPTY_REQUEST_DLC,
        )
        protocol.check_response_status(response)

    def disable(self, timeout_ms: float = 100) -> None:
        """Disable the L30 hand motor control state.

        Args:
            timeout_ms: Time to wait for the L30 v2 write ACK.

        Raises:
            ValidationError: If timeout_ms is invalid.
            TimeoutError: If no matching ACK is received before the timeout.
            ProtocolError: If the ACK reports a non-zero status byte.
        """
        response = self._client.request_ack(
            parent=protocol.L30_PARENT_CONTROL,
            subcmd=protocol.L30_SUBCMD_DISABLE,
            payload=protocol.empty_request_payload(),
            timeout_ms=timeout_ms,
            dlc=protocol.L30_EMPTY_REQUEST_DLC,
        )
        protocol.check_response_status(response)
