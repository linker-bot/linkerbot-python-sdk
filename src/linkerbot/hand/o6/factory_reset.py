"""Factory reset functionality for O6 robotic hand.

This module provides the FactoryResetManager class for restoring
device settings to factory defaults.
"""

import threading

import can

from linkerbot.comm import CANMessageDispatcher
from linkerbot.exceptions import TimeoutError, ValidationError


class FactoryResetManager:
    """Manager for factory reset operations.

    This class provides a method to restore all device parameters to factory defaults.
    This is a destructive operation that cannot be undone.

    The device requires at least 100ms to complete the reset operation.
    """

    _CMD = 0xCE
    _DATA_LENGTH = 8
    _CONFIRM_VALUE = 0x01

    def __init__(self, arbitration_id: int, dispatcher: CANMessageDispatcher) -> None:
        """Initialize the factory reset manager.

        Args:
            arbitration_id: CAN arbitration ID for factory reset command.
            dispatcher: CAN message dispatcher to use for communication.
        """
        self._arbitration_id = arbitration_id
        self._dispatcher = dispatcher
        self._dispatcher.subscribe(self._on_message)

        # Blocking reset support
        self._reset_waiters: list[tuple[threading.Event, dict]] = []
        self._reset_lock = threading.Lock()

    def reset_to_factory(self, timeout_ms: float = 100) -> None:
        """Restore all device parameters to factory defaults.

        This method sends a factory reset command to the device. All configuration
        parameters (angles, torques, speeds, stall settings, calibration, CAN ID, etc.)
        will be restored to their factory default values.

        Args:
            timeout_ms: Maximum time to wait for confirmation in milliseconds (default: 100).

        Raises:
            TimeoutError: If no confirmation is received within timeout.
            ValidationError: If timeout_ms is not positive.

        Example:
            >>> manager = FactoryResetManager(arbitration_id, dispatcher)
            >>> # Confirm with user before resetting
            >>> user_confirmed = input("Reset to factory defaults? (yes/no): ")
            >>> if user_confirmed.lower() == "yes":
            ...     try:
            ...         manager.reset_to_factory()
            ...         print("Factory reset confirmed. Device may require reconfiguration.")
            ...     except TimeoutError:
            ...         print("Factory reset timed out - device may not have responded.")
        """
        if timeout_ms <= 0:
            raise ValidationError("timeout_ms must be positive")

        event = threading.Event()
        result_holder: dict[str, bool] = {"success": False}

        # Register this waiter
        with self._reset_lock:
            self._reset_waiters.append((event, result_holder))

        # Build reset command: 8 bytes all set to 0xCE
        data = [self._CMD] * self._DATA_LENGTH

        msg = can.Message(
            arbitration_id=self._arbitration_id,
            data=data,
            is_extended_id=False,
        )

        self._dispatcher.send(msg)

        # Wait for confirmation or timeout
        if event.wait(timeout_ms / 1000.0):
            if not result_holder["success"]:
                raise TimeoutError(
                    f"Factory reset failed - no confirmation within {timeout_ms}ms"
                )
        else:
            # Timeout - remove ourselves from waiters list
            with self._reset_lock:
                if (event, result_holder) in self._reset_waiters:
                    self._reset_waiters.remove((event, result_holder))
            raise TimeoutError(
                f"Factory reset timed out - no response within {timeout_ms}ms"
            )

    def _on_message(self, msg: can.Message) -> None:
        # Filter: only process messages with correct arbitration ID
        if msg.arbitration_id != self._arbitration_id:
            return

        if len(msg.data) < 2:
            return

        cmd = msg.data[0]

        # Handle reset confirmation: 0xCE 0x01
        if cmd == self._CMD and msg.data[1] == self._CONFIRM_VALUE:
            with self._reset_lock:
                for event, result_holder in self._reset_waiters:
                    result_holder["success"] = True
                    event.set()
                self._reset_waiters.clear()
