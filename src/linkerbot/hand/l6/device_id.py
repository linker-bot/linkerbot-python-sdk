"""Device ID configuration for L6 robotic hand.

This module provides the DeviceIDManager class for configuring
device CAN bus IDs (TX ID and RX ID) online.
"""

import threading
import time
from dataclasses import dataclass

import can

from linkerbot.comm import CANMessageDispatcher
from linkerbot.exceptions import TimeoutError, ValidationError


@dataclass(frozen=True)
class DeviceIDs:
    """Device CAN bus ID configuration.

    Attributes:
        tx_id: Transmit ID - source address used by device when sending CAN messages (0-255).
        rx_id: Receive ID - target address that device listens to (0-255).
        timestamp: Unix timestamp when the data was retrieved.
    """

    tx_id: int
    rx_id: int
    timestamp: float


class DeviceIDManager:
    """Manager for device CAN bus ID configuration.

    This class provides methods to configure the device's transmit and receive IDs
    for CAN bus communication. Changes take effect immediately and are persisted.

    Available operations:
    - set_tx_id(): Configure device transmit ID (source address)
    - set_rx_id(): Configure device receive ID (target address)
    """

    _CMD = 0xC3
    _SUBCMD_SET_TX = 0x01
    _SUBCMD_SET_RX = 0x02
    _SAVE_CMD = 0xCF

    def __init__(self, arbitration_id: int, dispatcher: CANMessageDispatcher) -> None:
        """Initialize the device ID manager.

        Args:
            arbitration_id: CAN arbitration ID for device ID configuration.
            dispatcher: CAN message dispatcher to use for communication.
        """
        self._arbitration_id = arbitration_id
        self._dispatcher = dispatcher
        self._dispatcher.subscribe(self._on_message)

        # Blocking mode support
        self._blocking_waiters: list[tuple[threading.Event, dict]] = []
        self._waiters_lock = threading.Lock()

        # Save operation support
        self._save_waiters: list[tuple[threading.Event, dict]] = []
        self._save_lock = threading.Lock()

    def set_tx_id(self, tx_id: int, timeout_ms: float = 100) -> DeviceIDs:
        """Set device transmit ID (source address for outgoing messages).

        This method changes the ID that the device uses as the source address when
        sending CAN messages. The change takes effect immediately and is automatically
        saved to non-volatile memory.

        Args:
            tx_id: New transmit ID (0-255).
            timeout_ms: Maximum time to wait for confirmation in milliseconds (default: 100).

        Returns:
            DeviceIDs containing the updated TX ID and current RX ID.

        Raises:
            TimeoutError: If no confirmation is received within timeout.
            ValidationError: If tx_id is out of range or timeout_ms is not positive.

        Example:
            >>> manager = DeviceIDManager(arbitration_id, dispatcher)
            >>> ids = manager.set_tx_id(0x10)
            >>> print(f"TX ID: {ids.tx_id}, RX ID: {ids.rx_id}")
        """
        if timeout_ms <= 0:
            raise ValidationError("timeout_ms must be positive")
        if not 0 <= tx_id <= 255:
            raise ValidationError(f"tx_id must be in range [0, 255], got {tx_id}")

        result = self._set_id(self._SUBCMD_SET_TX, tx_id, timeout_ms)
        self._save_parameters()
        return result

    def set_rx_id(self, rx_id: int, timeout_ms: float = 100) -> DeviceIDs:
        """Set device receive ID (target address for incoming messages).

        This method changes the ID that the device listens to. Only messages with
        this ID as the target address will be received. The change takes effect immediately
        and is automatically saved to non-volatile memory.

        Args:
            rx_id: New receive ID (0-255).
            timeout_ms: Maximum time to wait for confirmation in milliseconds (default: 100).

        Returns:
            DeviceIDs containing current TX ID and the updated RX ID.

        Raises:
            TimeoutError: If no confirmation is received within timeout.
            ValidationError: If rx_id is out of range or timeout_ms is not positive.

        Example:
            >>> manager = DeviceIDManager(arbitration_id, dispatcher)
            >>> ids = manager.set_rx_id(0x20)
            >>> print(f"TX ID: {ids.tx_id}, RX ID: {ids.rx_id}")
        """
        if timeout_ms <= 0:
            raise ValidationError("timeout_ms must be positive")
        if not 0 <= rx_id <= 255:
            raise ValidationError(f"rx_id must be in range [0, 255], got {rx_id}")

        result = self._set_id(self._SUBCMD_SET_RX, rx_id, timeout_ms)
        self._save_parameters()
        return result

    def _save_parameters(self, timeout_ms: float = 200) -> None:
        """Save current device ID configuration to non-volatile memory.

        This method sends a save command to persist the current device ID
        configuration (TX ID and RX ID) so they are retained after power cycling.

        Args:
            timeout_ms: Maximum time to wait for save confirmation in milliseconds (default: 200).

        Raises:
            TimeoutError: If no confirmation is received within timeout.
            ValidationError: If timeout_ms is not positive.

        Example:
            >>> manager = DeviceIDManager(arbitration_id, dispatcher)
            >>> # Configure device IDs
            >>> manager.set_tx_id(0x10)
            >>> manager.set_rx_id(0x20)
            >>> # Save to non-volatile memory
            >>> try:
            ...     manager.save_parameters()
            ...     print("Device IDs saved successfully")
            ... except TimeoutError:
            ...     print("Save operation timed out")
        """
        if timeout_ms <= 0:
            raise ValidationError("timeout_ms must be positive")

        event = threading.Event()
        result_holder: dict[str, bool] = {"success": False}

        # Register this waiter
        with self._save_lock:
            self._save_waiters.append((event, result_holder))

        # Send save command (8 bytes, all 0xCF)
        data = [self._SAVE_CMD] * 8
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
                    f"Save operation failed - no confirmation within {timeout_ms}ms"
                )
        else:
            # Timeout - remove ourselves from waiters list
            with self._save_lock:
                if (event, result_holder) in self._save_waiters:
                    self._save_waiters.remove((event, result_holder))
            raise TimeoutError(
                f"Save operation timed out - no response within {timeout_ms}ms"
            )

    def _set_id(self, subcmd: int, id_value: int, timeout_ms: float) -> DeviceIDs:
        event = threading.Event()
        result_holder: dict[str, DeviceIDs | None] = {"data": None}

        # Register this waiter
        with self._waiters_lock:
            self._blocking_waiters.append((event, result_holder))

        # Send set command
        data = [self._CMD, subcmd, id_value]
        msg = can.Message(
            arbitration_id=self._arbitration_id,
            data=data,
            is_extended_id=False,
        )
        self._dispatcher.send(msg)

        # Wait for response
        if event.wait(timeout_ms / 1000.0):
            if result_holder["data"] is None:
                raise TimeoutError(f"No confirmation received within {timeout_ms}ms")
            return result_holder["data"]
        else:
            # Timeout - remove ourselves from waiters list
            with self._waiters_lock:
                if (event, result_holder) in self._blocking_waiters:
                    self._blocking_waiters.remove((event, result_holder))
            raise TimeoutError(
                f"Device ID set operation timed out after {timeout_ms}ms"
            )

    def _on_message(self, msg: can.Message) -> None:
        # Internal callback
        if msg.arbitration_id != self._arbitration_id:
            return

        if len(msg.data) < 1:
            return

        cmd = msg.data[0]

        # Handle device ID response messages
        if cmd == self._CMD and len(msg.data) >= 3:
            # Parse device IDs from response: [0xC3, tx_id, rx_id]
            tx_id = msg.data[1]
            rx_id = msg.data[2]

            device_ids = DeviceIDs(tx_id=tx_id, rx_id=rx_id, timestamp=time.time())
            self._on_complete_data(device_ids)

        # Handle save confirmation messages
        elif cmd == self._SAVE_CMD and len(msg.data) >= 2:
            # Check for success response: 0xCF 0x01
            if msg.data[1] == 0x01:
                # Wake up all save waiters
                with self._save_lock:
                    for event, result_holder in self._save_waiters:
                        result_holder["success"] = True
                        event.set()
                    self._save_waiters.clear()

    def _on_complete_data(self, data: DeviceIDs) -> None:
        # Internal: Handle complete device IDs data
        # Wake up all blocking waiters
        with self._waiters_lock:
            for event, result_holder in self._blocking_waiters:
                result_holder["data"] = data
                event.set()
            self._blocking_waiters.clear()
