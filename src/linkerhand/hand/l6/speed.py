"""Speed control and sensing for L6 robotic hand.

This module provides the SpeedManager class for controlling motor speeds
and reading speed sensor data via CAN bus communication.
"""

import can

from linkerhand.comm import CANMessageDispatcher
from linkerhand.exceptions import ValidationError

from .types import L6Speed


class SpeedManager:
    """Manager for motor speed control.

    This class handles speed control operations by sending target speeds
    to the robotic hand motors.
    """

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

    def set_speeds(self, speeds: L6Speed | list[float]) -> None:
        """Send target speeds to the robotic hand motors.

        This method sends 6 target speeds to the hand.

        Args:
            speeds: L6Speed instance or list of 6 target speeds (range 0-100 each).

        Raises:
            ValidationError: If speeds count is not 6 or values are out of range.

        Example:
            >>> manager = SpeedManager(arbitration_id, dispatcher)
            >>> # Using L6Speed instance
            >>> manager.set_speeds(L6Speed(thumb_flex=50.0, thumb_abd=50.0,
            ...                            index=50.0, middle=50.0, ring=50.0, pinky=50.0))
            >>> # Using list
            >>> manager.set_speeds([50.0, 50.0, 50.0, 50.0, 50.0, 50.0])
        """
        if isinstance(speeds, L6Speed):
            raw_speeds = speeds.to_raw()
        elif isinstance(speeds, list):
            # Validate input
            if len(speeds) != self._SPEED_COUNT:
                raise ValidationError(
                    f"Expected {self._SPEED_COUNT} speeds, got {len(speeds)}"
                )
            # Validate speed values (0-100 range)
            for i, speed in enumerate(speeds):
                if not isinstance(speed, float):
                    raise ValidationError(f"Speed {i} must be float, got {type(speed)}")
                if not 0 <= speed <= 100:
                    raise ValidationError(
                        f"Speed {i} value {speed} out of range [0, 100]"
                    )
            raw_speeds = L6Speed.from_list(speeds).to_raw()

        # Build and send message
        data = [self._CONTROL_CMD, *raw_speeds]
        msg = can.Message(
            arbitration_id=self._arbitration_id,
            data=data,
            is_extended_id=False,
        )
        self._dispatcher.send(msg)
