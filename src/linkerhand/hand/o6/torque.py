"""Torque control for O6 robotic hand.

This module provides the TorqueManager class for controlling joint torque
via CAN bus communication.
"""

import time
from dataclasses import dataclass

import can

from linkerhand.comm import CANMessageDispatcher
from linkerhand.exceptions import ValidationError


@dataclass(frozen=True)
class TorqueData:
    """Immutable torque data container.

    Attributes:
        torques: Tuple of joint torques (6 values, range 0-255).
        timestamp: Unix timestamp when the data was received.
    """

    torques: tuple
    timestamp: float


class TorqueManager:
    """Manager for joint torque limit control via CAN bus.

    This class handles torque operations with two access modes:
    1. Torque limit control: set_torques() - send 6 target torque
    2. Cache reading: get_current_torques() - non-blocking read of cached torques

    The manager uses an immutable data design for thread-safe operation without locks
    for data access. All CAN message processing happens in the dispatcher's thread.

    CAN Protocol:
        - Control: Send [0x02, torque1...torque6] -> Receive [0x02, torque1...torque6]
        The response echoes the sent torque data.

    Attributes:
        _dispatcher: CAN message dispatcher for send/receive operations.
        _latest_data: Most recently received torque data (or None).
    """

    # CAN protocol constants
    _CONTROL_CMD = 0x02
    _TORQUE_COUNT = 6

    def __init__(self, arbitration_id: int, dispatcher: CANMessageDispatcher) -> None:
        """Initialize the torque manager.

        Args:
            arbitration_id: CAN arbitration ID for torque control.
            dispatcher: CAN message dispatcher to use for communication.
        """
        self._arbitration_id = arbitration_id
        self._dispatcher = dispatcher
        self._dispatcher.subscribe(self._on_message)

        # Latest torque data cache
        self._latest_data: TorqueData | None = None

    def set_torques(self, torques: tuple[int, ...] | list[int]) -> None:
        """Send target torques to the robotic hand.

        This method sends 6 target torques to the hand. The hand will respond
        by echoing the sent torque data, which are automatically cached and can be
        retrieved via get_current_torques().

        Args:
            torques: Tuple or list of 6 target torques (range 0-255 each).
                Values cannot be negative as they are encoded as unsigned bytes
                in the CAN protocol.

        Raises:
            ValidationError: If torques count is not 6 or values are out of range.

        Example:
            >>> manager = TorqueManager(arbitration_id, dispatcher)
            >>> manager.set_torques((100, 150, 200, 180, 160, 140))
            >>> time.sleep(0.1)  # Wait for response
            >>> current = manager.get_current_torques()
            >>> if current:
            ...     print(f"Current torques: {current.torques}")
        """
        # Validate input
        if len(torques) != self._TORQUE_COUNT:
            raise ValidationError(
                f"Expected {self._TORQUE_COUNT} torques, got {len(torques)}"
            )

        # Validate torque values (0-255 range for CAN byte encoding)
        # Note: Values cannot be negative as they are encoded as unsigned bytes
        for i, torque in enumerate(torques):
            if not isinstance(torque, int):
                raise ValidationError(f"Torque {i} must be int, got {type(torque)}")
            if not 0 <= torque <= 255:
                raise ValidationError(
                    f"Torque {i} value {torque} out of range [0, 255]"
                )

        # Build and send CAN message
        data = [self._CONTROL_CMD, *torques]
        msg = can.Message(
            arbitration_id=self._arbitration_id,
            data=data,
            is_extended_id=False,
        )
        self._dispatcher.send(msg)

    def get_current_torques(self) -> TorqueData | None:
        """Get the most recent cached torque data (non-blocking).

        This method returns the last received torque data (from set_torques()
        response) without sending any new requests.

        Returns:
            TorqueData instance or None if no data received yet.

        Example:
            >>> data = manager.get_current_torques()
            >>> if data:
            ...     age = time.time() - data.timestamp
            ...     if age < 0.1:  # Less than 100ms old
            ...         print(f"Fresh torques: {data.torques}")
        """
        return self._latest_data

    def _on_message(self, msg: can.Message) -> None:
        """Handle incoming CAN messages (callback from dispatcher thread).

        Filters for torque response messages and updates cache. The response
        echoes the sent torque data.

        Args:
            msg: CAN message from the bus.

        Note:
            This method executes in the dispatcher's receive thread and must
            return quickly to avoid blocking message reception.
        """
        # Filter: only process messages with correct arbitration ID
        if msg.arbitration_id != self._arbitration_id:
            return

        # Filter: only process torque response messages (start with 0x02)
        if len(msg.data) < 2 or msg.data[0] != self._CONTROL_CMD:
            return

        # Parse torque data (skip first byte which is the command)
        torques = tuple(msg.data[1:])

        # Validate torque count (should be 6 torques)
        if len(torques) != self._TORQUE_COUNT:
            return

        # Create immutable torque data
        torque_data = TorqueData(torques=torques, timestamp=time.time())

        # Dispatch to cache
        self._on_complete_data(torque_data)

    def _on_complete_data(self, data: TorqueData) -> None:
        """Handle complete torque data by updating cache.

        This method updates the cached latest data.

        Args:
            data: Complete torque data to cache.

        Note:
            This method executes in the dispatcher's receive thread.
        """
        # Update cache (atomic reference assignment)
        self._latest_data = data
