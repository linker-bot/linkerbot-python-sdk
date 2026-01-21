"""O6 robotic hand control interface.

This module provides the main O6 class for controlling the O6 robotic hand
via CAN bus communication. It integrates angle control, torque control,
speed control, and temperature sensing into a unified interface.
"""

from typing import Literal

from linkerhand.comm import CANMessageDispatcher
from linkerhand.exceptions import StateError

from .angle import AngleManager
from .speed import SpeedManager
from .temperature import TemperatureManager
from .torque import TorqueManager


class O6:
    """Main interface for O6 robotic hand control.

    This class provides a unified interface for controlling the O6 robotic hand,
    integrating angle control, torque control, speed control, and temperature
    sensing. It manages the CAN bus connection and coordinates all subsystems.

    The O6 class should be used as a context manager to ensure proper resource
    cleanup:

    ```python
    with O6(side='left', interface_name='can0') as hand:
        # Control angles
        hand.angle.set_angles((10, 20, 30, 40, 50, 60))

        # Control speeds
        hand.speed.set_speeds((100, 100, 100, 100, 100, 100))

        # Control accelerations
        hand.speed.set_accelerations((50, 50, 50, 50, 50, 50))

        # Get temperature data
        temps = hand.temperature.get_temperatures_blocking(timeout_ms=500)

        # Control torque
        hand.torque.set_torques((100, 150, 200, 180, 160, 140))
    ```

    Attributes:
        angle: AngleManager instance for joint angle control and sensing.
        torque: TorqueManager instance for joint torque limit control and sensing.
        speed: SpeedManager instance for motor speed and acceleration control.
        temperature: TemperatureManager instance for joint temperature sensing.
    """

    def __init__(
        self,
        side: Literal["left", "right"],
        interface_name: str,
        interface_type: str = "socketcan",
    ) -> None:
        """Initialize the O6 robotic hand interface.

        Args:
            side: Hand side ('left' or 'right').
            interface_name: Name of the CAN interface (e.g., 'can0', 'vcan0').
            interface_type: Type of CAN interface backend (default: 'socketcan').

        Example:
            >>> hand = O6('left', 'can0')
            >>> hand.__enter__()  # Or use with statement
            >>> hand.angle.set_angles((10, 20, 30, 40, 50, 60))
            >>> hand.close()

        Note:
            The CAN dispatcher is automatically started when entering the context manager.
            Always call close() or use the context manager to ensure proper cleanup.
        """
        # Create CAN message dispatcher
        self._dispatcher = CANMessageDispatcher(
            interface_name=interface_name, interface_type=interface_type
        )

        self._arbitration_id = 0x28
        if side == "right":
            self._arbitration_id = 0x27

        # Create subsystem managers
        self.angle = AngleManager(
            arbitration_id=self._arbitration_id, dispatcher=self._dispatcher
        )
        self.torque = TorqueManager(
            arbitration_id=self._arbitration_id, dispatcher=self._dispatcher
        )
        self.speed = SpeedManager(
            arbitration_id=self._arbitration_id, dispatcher=self._dispatcher
        )
        self.temperature = TemperatureManager(
            arbitration_id=self._arbitration_id, dispatcher=self._dispatcher
        )

        # State tracking
        self._closed = False

    def __enter__(self) -> "O6":
        """Enter the context manager.

        The CAN dispatcher is already started in __init__, so this method
        simply returns self for use in with statements.

        Returns:
            Self for use in with statements.

        Example:
            >>> with O6('left', 'can0') as hand:
            ...     hand.angle.set_angles((10, 20, 30, 40, 50, 60))
        """
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        """Exit the context manager and clean up resources.

        Args:
            exc_type: Exception type if an exception occurred.
            exc_val: Exception value if an exception occurred.
            exc_tb: Exception traceback if an exception occurred.

        Returns:
            False to propagate exceptions.

        Note:
            This method calls close() to ensure proper resource cleanup.
        """
        self.close()
        return False  # Don't suppress exceptions

    def close(self) -> None:
        """Close the O6 interface and release all resources.

        This method:
        1. Stops streaming mode for all sensors (angle, temperature)
        2. Stops the CAN message dispatcher
        3. Marks the interface as closed

        This method is idempotent and safe to call multiple times.

        Example:
            >>> hand = O6('left', 'can0')
            >>> hand.angle.set_angles((10, 20, 30, 40, 50, 60))
            >>> hand.close()  # Clean up resources

        Raises:
            No exceptions are raised during cleanup to ensure resources
            are released even if errors occur.
        """
        if self._closed:
            return

        try:
            # Stop streaming modes (angle and temperature have streaming, torque and speed don't)
            self.angle.stop_streaming()
            self.temperature.stop_streaming()
        except Exception:
            # Ignore errors during cleanup
            pass

        try:
            # Stop CAN dispatcher
            self._dispatcher.stop()
        except Exception:
            # Ignore errors during cleanup
            pass

        self._closed = True

    def __del__(self) -> None:
        """Destructor for defensive resource cleanup.

        Calls close() to ensure resources are released if the user
        forgot to close the interface properly.

        Note:
            This is a defensive measure. Users should always explicitly
            close() or use the context manager.
        """
        self.close()

    def is_closed(self) -> bool:
        """Check if the interface has been closed.

        Returns:
            True if the interface is closed, False otherwise.

        Example:
            >>> hand = O6('left', 'can0')
            >>> print(hand.is_closed())  # False
            >>> hand.close()
            >>> print(hand.is_closed())  # True
        """
        return self._closed

    def _ensure_open(self) -> None:
        """Ensure the interface is open.

        Raises:
            StateError: If the interface has been closed.

        Note:
            This is a helper method for subsystems to check state.
        """
        if self._closed:
            raise StateError(
                "O6 interface is closed. Create a new instance or use context manager."
            )
