"""L6 robotic hand control interface.

This module provides the main L6 class for controlling the L6 robotic hand
via CAN bus communication. It integrates angle control and force sensor
data acquisition into a unified interface.
"""

from typing import Literal

from linkerbot.comm import CANMessageDispatcher
from linkerbot.exceptions import StateError

from .angle import AngleManager
from .current import CurrentManager
from .device_id import DeviceIDManager
from .factory_reset import FactoryResetManager
from .fault import FaultManager
from .force_sensor import ForceSensorManager
from .limit_compensation import LimitCompensationManager
from .speed import SpeedManager
from .stall import StallManager
from .temperature import TemperatureManager
from .torque import TorqueManager
from .version import VersionManager


class L6:
    """Main interface for L6 robotic hand control.

    This class provides a unified interface for controlling the L6 robotic hand,
    integrating angle control, speed control and force sensor data acquisition. It manages the
    CAN bus connection and coordinates all subsystems.

    The L6 class should be used as a context manager to ensure proper resource
    cleanup:

    ```python
    with L6(side='left', interface_name='can0') as hand:
        # Control angles
        hand.angle.set_angles((10, 20, 30, 40, 50, 60))

        # Control speeds
        hand.speed.set_speeds((100, 100, 100, 100, 100, 100))

        # Get force sensor data for all fingers
        all_sensors = hand.force_sensor.get_all_data_blocking(timeout_ms=500)

        # Get temperature data for all fingers
        all_temperatures = hand.temperature.get_temperatures_blocking(timeout_ms=500)

        # Get current data for all fingers
        all_currents = hand.current.get_currents_blocking(timeout_ms=500)

        # Or get data for a specific finger
        thumb_data = hand.force_sensor.get_finger('thumb').get_data_blocking()

        # Control torques
        hand.torque.set_torques((100, 150, 200, 180, 160, 140))

        # Clear all faults
        hand.fault.clear_faults()

        # Read fault status
        fault_data = hand.fault.get_faults_blocking(timeout_ms=500)
        if fault_data.faults.has_any_fault():
            # Check specific joint
            if fault_data.faults.thumb_flex.has_fault():
                print(f"Thumb flex: {fault_data.faults.thumb_flex.get_fault_names()}")
            # Check index finger
            if fault_data.faults.index.has_fault():
                print(f"Index: {fault_data.faults.index.get_fault_names()}")

        # Configure stall detection
        hand.stall.set_stall_time([500.0, 500.0, 500.0, 500.0, 500.0, 500.0])  # 500ms
        hand.stall.set_stall_threshold([500.0, 500.0, 500.0, 500.0, 500.0, 500.0])  # 500mA
        hand.stall.set_stall_torque([700.0, 700.0, 700.0, 700.0, 700.0, 700.0])  # 700mA

        # Get device version information
        device_info = hand.version.get_device_info()
        print(f"Serial Number: {device_info.serial_number}")
        print(f"PCB Version: {device_info.pcb_version}")
        print(f"Firmware Version: {device_info.firmware_version}")
        print(f"Mechanical Version: {device_info.mechanical_version}")

        # Configure joint limit compensation
        hand.limit_compensation.set_limit_compensation([50, 30, 60, 60, 60, 60])
        comp_data = hand.limit_compensation.get_limit_compensation_blocking()
        print(f"Limit compensation: {comp_data.compensation.thumb_flex}")

        # Configure device CAN IDs
        device_ids = hand.device_id.set_tx_id(0x10)
        print(f"TX ID: {device_ids.tx_id}, RX ID: {device_ids.rx_id}")

        # Factory reset (USE WITH CAUTION!)
        # hand.factory_reset.reset_to_factory()
    ```

    Attributes:
        angle: AngleManager instance for joint angle control and sensing.
        speed: SpeedManager instance for motor speed control and sensing.
        force_sensor: ForceSensorManager instance for force sensor data acquisition.
        torque: TorqueManager instance for joint torque control and sensing.
        temperature: TemperatureManager instance for temperature data acquisition.
        current: CurrentManager instance for current data acquisition.
        fault: FaultManager instance for fault clearing and status reading.
        stall: StallManager instance for stall detection configuration.
        version: VersionManager instance for device version information.
        limit_compensation: LimitCompensationManager instance for joint limit compensation configuration.
        device_id: DeviceIDManager instance for device CAN ID configuration.
        factory_reset: FactoryResetManager instance for factory reset operations.
    Args:
        side: Side of the hand (left or right, default: left).
        interface_name: Name of the CAN interface (e.g., 'can0', 'vcan0').
        interface_type: Type of CAN interface backend (default: 'socketcan').
    """

    def __init__(
        self,
        side: Literal["left", "right"],
        interface_name: str,
        interface_type: str = "socketcan",
    ) -> None:
        """Initialize the L6 robotic hand interface.

        Args:
            side: Side of the hand (left or right, default: left).
            interface_name: Name of the CAN interface (e.g., 'can0', 'vcan0').
            interface_type: Type of CAN interface backend (default: 'socketcan').

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
        self.force_sensor = ForceSensorManager(
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
        self.current = CurrentManager(
            arbitration_id=self._arbitration_id, dispatcher=self._dispatcher
        )
        self.fault = FaultManager(
            arbitration_id=self._arbitration_id, dispatcher=self._dispatcher
        )
        self.stall = StallManager(
            arbitration_id=self._arbitration_id, dispatcher=self._dispatcher
        )
        self.version = VersionManager(
            arbitration_id=self._arbitration_id, dispatcher=self._dispatcher
        )
        self.limit_compensation = LimitCompensationManager(
            arbitration_id=self._arbitration_id, dispatcher=self._dispatcher
        )
        self.device_id = DeviceIDManager(
            arbitration_id=self._arbitration_id, dispatcher=self._dispatcher
        )
        self.factory_reset = FactoryResetManager(
            arbitration_id=self._arbitration_id, dispatcher=self._dispatcher
        )
        # State tracking
        self._closed = False

    def __enter__(self) -> "L6":
        """Enter the context manager.

        The CAN dispatcher is already started in __init__, so this method
        simply returns self for use in with statements.

        Returns:
            Self for use in with statements.

        Example:
            >>> with L6('left', 'can0') as hand:
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
        """Close the L6 interface and release all resources.

        This method is idempotent and safe to call multiple times.

        Example:
            >>> hand = L6('left', 'can0')
            >>> hand.angle.set_angles((10, 20, 30, 40, 50, 60))
            >>> hand.close()  # Clean up resources
        """
        if self._closed:
            return

        try:
            # Stop streaming modes
            self.force_sensor.stop_streaming()
            self.angle.stop_streaming()
            self.torque.stop_streaming()
            self.temperature.stop_streaming()
            self.current.stop_streaming()
            self.fault.stop_streaming()
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
            >>> hand = L6('left', 'can0')
            >>> print(hand.is_closed())  # False
            >>> hand.close()
            >>> print(hand.is_closed())  # True
        """
        return self._closed

    def _ensure_open(self) -> None:
        if self._closed:
            raise StateError(
                "L6 interface is closed. Create a new instance or use context manager."
            )
