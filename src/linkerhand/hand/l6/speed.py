"""Speed control and sensing for L6 robotic hand.

This module provides the SpeedManager class for controlling motor speeds
and reading speed sensor data via CAN bus communication.
"""

import can

from linkerhand.comm import CANMessageDispatcher
from linkerhand.exceptions import ValidationError


class SpeedManager:
    """Manager for motor speed control via CAN bus.

    This class handles speed control operations by sending target speeds
    to the robotic hand motors.

    CAN Protocol:
        - Control: Send [0x05, speed1...speed6]

    Attributes:
        _arbitration_id: CAN arbitration ID for speed control.
        _dispatcher: CAN message dispatcher for send operations.
    """

    # CAN protocol constants
    _CONTROL_CMD = 0x05
    _SPEED_COUNT = 6

    def __init__(self, arbitration_id: int, dispatcher: CANMessageDispatcher) -> None:
        """Initialize the speed manager.

        Args:
            arbitration_id: CAN arbitration ID for speed control.
            dispatcher: CAN message dispatcher to use for communication.
        """
        self._arbitration_id = arbitration_id
        self._dispatcher = dispatcher

    def set_speeds(self, speeds: tuple[int, ...] | list[int]) -> None:
        """Send target speeds to the robotic hand motors.

        This method sends 6 target speeds to the hand.

        Args:
            speeds: Tuple or list of 6 target speeds (range 0-255).

        Raises:
            ValidationError: If speeds count is not 6 or values are out of range.

        Example:
            >>> manager = SpeedManager(arbitration_id, dispatcher)
            >>> manager.set_speeds((100, 100, 100, 100, 100, 100))
        """
        # Validate input
        if len(speeds) != self._SPEED_COUNT:
            raise ValidationError(
                f"Expected {self._SPEED_COUNT} speeds, got {len(speeds)}"
            )

        # Validate speed values (0-255 range for CAN byte encoding)
        for i, speed in enumerate(speeds):
            if not isinstance(speed, int):
                raise ValidationError(f"Speed {i} must be int, got {type(speed)}")
            if not 0 <= speed <= 255:
                raise ValidationError(f"Speed {i} value {speed} out of range [0, 255]")

        # Build and send CAN message
        data = [self._CONTROL_CMD, *speeds]
        msg = can.Message(
            arbitration_id=self._arbitration_id,
            data=data,
            is_extended_id=False,
        )
        self._dispatcher.send(msg)
