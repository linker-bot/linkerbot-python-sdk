"""Factory reset functionality for L6 robotic hand.

This module provides the FactoryResetManager class for restoring
device settings to factory defaults.
"""

import can

from linkerbot.comm import CANMessageDispatcher


class FactoryResetManager:
    """Manager for factory reset operations.

    This class provides a method to restore all device parameters to factory defaults.
    This is a destructive operation that cannot be undone.

    ⚠️  WARNING: Factory reset will erase all custom configurations!

    The device requires at least 80ms to complete the reset operation.
    """

    _CMD = 0xCE
    _DATA_LENGTH = 7

    def __init__(self, arbitration_id: int, dispatcher: CANMessageDispatcher) -> None:
        """Initialize the factory reset manager.

        Args:
            arbitration_id: CAN arbitration ID for factory reset command.
            dispatcher: CAN message dispatcher to use for communication.
        """
        self._arbitration_id = arbitration_id
        self._dispatcher = dispatcher

    def reset_to_factory(self) -> None:
        """Restore all device parameters to factory defaults.

        This method sends a factory reset command to the device. All configuration
        parameters (angles, torques, speeds, stall settings, calibration, etc.) will
        be restored to their factory default values.

        ⚠️  WARNING: This is a destructive operation that cannot be undone!
        - All custom configurations will be lost
        - Device may require recalibration after reset
        - Allow at least 80ms for the reset operation to complete

        The device does not send an explicit confirmation response. After calling this
        method, you should wait at least 80ms before sending additional commands.

        Example:
            >>> manager = FactoryResetManager(arbitration_id, dispatcher)
            >>> # Confirm with user before resetting
            >>> user_confirmed = input("Reset to factory defaults? (yes/no): ")
            >>> if user_confirmed.lower() == "yes":
            ...     manager.reset_to_factory()
            ...     print("Factory reset command sent. Waiting for device to reset...")
            ...     time.sleep(0.1)  # Wait 100ms for reset to complete
            ...     print("Reset complete. Device may require reconfiguration.")
        """
        # Build reset command: 7 bytes all set to 0xCE
        data = [self._CMD] * self._DATA_LENGTH

        msg = can.Message(
            arbitration_id=self._arbitration_id,
            data=data,
            is_extended_id=False,
        )

        self._dispatcher.send(msg)
        # Note: No response expected from device
