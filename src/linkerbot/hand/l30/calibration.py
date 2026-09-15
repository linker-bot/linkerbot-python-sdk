"""Zero-point calibration for the L30 robotic hand."""

from __future__ import annotations

from linkerbot.exceptions import ValidationError

from . import protocol
from .client import L30Client
from .control import ControlManager

_DEFAULT_CALIBRATION_TIMEOUT_MS = 1000


class CalibrationManager:
    """Manager for the destructive L30 all-joint zero-point calibration.

    A calibration request writes the current mechanical positions of J1..J17
    to EEPROM as their new zero references. The manager enforces the protocol
    sequence: global disable, configuration unlock, then zero calibration.
    """

    def __init__(self, client: L30Client, control: ControlManager) -> None:
        """Initialize the calibration manager.

        Args:
            client: L30 protocol client used to send configuration commands.
            control: Control manager used to globally disable every joint.
        """
        self._client = client
        self._control = control

    def calibrate_zero(
        self,
        *,
        confirm: bool = False,
        timeout_ms: float = _DEFAULT_CALIBRATION_TIMEOUT_MS,
    ) -> None:
        """Set all current mechanical joint positions as their new zero points.

        This operation first globally disables all joints, unlocks device
        configuration with the protocol-defined password, and then starts the
        all-joint calibration. Every step must receive a successful ACK before
        the next request is sent. The method does not re-enable the joints.

        Args:
            confirm: Must be exactly True to acknowledge that calibration writes
                the current J1..J17 positions to EEPROM as new zero references.
            timeout_ms: Time to wait for each of the three protocol ACKs.

        Raises:
            ValidationError: If confirm is not True or timeout_ms is invalid.
            TimeoutError: If an ACK is not received before the timeout.
            ProtocolError: If disable, unlock, or calibration reports an error.
        """
        if confirm is not True:
            raise ValidationError(
                "confirm=True is required because zero calibration writes the "
                "current joint positions to EEPROM"
            )

        self._control.disable(timeout_ms=timeout_ms)
        self._unlock_configuration(timeout_ms=timeout_ms)

        response = self._client.request_ack(
            parent=protocol.L30_PARENT_CONFIG,
            subcmd=protocol.L30_SUBCMD_ZERO_CALIBRATION,
            payload=protocol.empty_request_payload(),
            timeout_ms=timeout_ms,
            dlc=protocol.L30_EMPTY_REQUEST_DLC,
        )
        protocol.check_response_status(response)

    def _unlock_configuration(self, *, timeout_ms: float) -> None:
        response = self._client.request_ack(
            parent=protocol.L30_PARENT_CONFIG,
            subcmd=protocol.L30_SUBCMD_CONFIG_UNLOCK,
            payload=protocol.encode_config_unlock(),
            timeout_ms=timeout_ms,
            dlc=protocol.L30_CONFIG_UNLOCK_DLC,
        )
        protocol.check_response_status(response)
