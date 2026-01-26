"""Speed and acceleration control for O6 robotic hand.

This module provides the SpeedManager class for controlling motor speeds
and accelerations via CAN bus communication.
"""

import time
from dataclasses import dataclass

import can

from linkerhand.comm import CANMessageDispatcher
from linkerhand.exceptions import ValidationError


@dataclass(frozen=True)
class SpeedData:
    """Immutable speed data container.

    Attributes:
        speeds: Tuple of joint speeds (6 values, range 0-255).
        timestamp: Unix timestamp when the data was received.
    """

    speeds: tuple
    timestamp: float


@dataclass(frozen=True)
class AccelerationData:
    """Immutable acceleration data container.

    Attributes:
        accelerations: Tuple of joint accelerations (6 values, range 0-254).
        timestamp: Unix timestamp when the data was received.
    """

    accelerations: tuple
    timestamp: float


class SpeedManager:
    """Manager for motor speed and acceleration control via CAN bus.

    This class handles speed and acceleration control operations with the following
    access modes:
    1. Speed control: set_speeds() - send 6 target speeds
    2. Acceleration control: set_accelerations() - send 6 target accelerations
    3. Cache reading: get_current_speeds() - non-blocking read of cached speeds
    4. Cache reading: get_current_accelerations() - non-blocking read of cached accelerations

    The manager uses an immutable data design for thread-safe operation without locks
    for data access. All CAN message processing happens in the dispatcher's thread.

    CAN Protocol:
        - Speed control: Send [0x05, speed1...speed6] -> Receive [0x05, speed1...speed6]
        - Acceleration control: Send [0x07, accel1...accel6] -> Receive [0x07, accel1...accel6]
        The responses echo the sent data.

    Attributes:
        _arbitration_id: CAN arbitration ID for speed/acceleration control.
        _dispatcher: CAN message dispatcher for send/receive operations.
        _latest_speed_data: Most recently received speed data (or None).
        _latest_acceleration_data: Most recently received acceleration data (or None).
    """

    # CAN protocol constants
    _SPEED_CMD = 0x05
    _ACCELERATION_CMD = 0x07
    _SPEED_COUNT = 6

    def __init__(self, arbitration_id: int, dispatcher: CANMessageDispatcher) -> None:
        """Initialize the speed manager.

        Args:
            arbitration_id: CAN arbitration ID for speed/acceleration control.
            dispatcher: CAN message dispatcher to use for communication.
        """
        self._arbitration_id = arbitration_id
        self._dispatcher = dispatcher
        self._dispatcher.subscribe(self._on_message)

        # Latest speed and acceleration data cache
        self._latest_speed_data: SpeedData | None = None
        self._latest_acceleration_data: AccelerationData | None = None

    def set_speeds(self, speeds: tuple[int, ...] | list[int]) -> None:
        """Send target speeds to the robotic hand motors.

        This method sends 6 target speeds to the hand. The hand will respond
        by echoing the sent speed data, which are automatically cached and can be
        retrieved via get_current_speeds().

        Args:
            speeds: Tuple or list of 6 target speeds (range 0-255).

        Raises:
            ValidationError: If speeds count is not 6 or values are out of range.

        Example:
            >>> manager = SpeedManager(arbitration_id, dispatcher)
            >>> manager.set_speeds((100, 100, 100, 100, 100, 100))
            >>> time.sleep(0.1)  # Wait for response
            >>> current = manager.get_current_speeds()
            >>> if current:
            ...     print(f"Current speeds: {current.speeds}")
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
        data = [self._SPEED_CMD, *speeds]
        msg = can.Message(
            arbitration_id=self._arbitration_id,
            data=data,
            is_extended_id=False,
        )
        self._dispatcher.send(msg)

    def set_accelerations(self, accels: tuple[int, ...] | list[int]) -> None:
        """Send target accelerations to the robotic hand motors.

        This method sends 6 target accelerations to the hand. The hand will respond
        by echoing the sent acceleration data, which are automatically cached and can be
        retrieved via get_current_accelerations().

        Args:
            accels: Tuple or list of 6 target accelerations (range 0-254).

        Raises:
            ValidationError: If accels count is not 6 or values are out of range.

        Example:
            >>> manager = SpeedManager(arbitration_id, dispatcher)
            >>> manager.set_accelerations((50, 50, 50, 50, 50, 50))
            >>> time.sleep(0.1)  # Wait for response
            >>> current = manager.get_current_accelerations()
            >>> if current:
            ...     print(f"Current accelerations: {current.accelerations}")
        """
        # Validate input
        if len(accels) != self._SPEED_COUNT:
            raise ValidationError(
                f"Expected {self._SPEED_COUNT} accelerations, got {len(accels)}"
            )

        # Validate acceleration values (0-254 range for CAN byte encoding)
        for i, accel in enumerate(accels):
            if not isinstance(accel, int):
                raise ValidationError(
                    f"Acceleration {i} must be int, got {type(accel)}"
                )
            if not 0 <= accel <= 254:
                raise ValidationError(
                    f"Acceleration {i} value {accel} out of range [0, 254]"
                )

        # Build and send CAN message
        data = [self._ACCELERATION_CMD, *accels]
        msg = can.Message(
            arbitration_id=self._arbitration_id,
            data=data,
            is_extended_id=False,
        )
        self._dispatcher.send(msg)

    def get_current_speeds(self) -> SpeedData | None:
        """Get the most recent cached speed data (non-blocking).

        This method returns the last received speed data (from set_speeds()
        response) without sending any new requests.

        Returns:
            SpeedData instance or None if no data received yet.

        Example:
            >>> data = manager.get_current_speeds()
            >>> if data:
            ...     age = time.time() - data.timestamp
            ...     if age < 0.1:  # Less than 100ms old
            ...         print(f"Fresh speeds: {data.speeds}")
        """
        return self._latest_speed_data

    def get_current_accelerations(self) -> AccelerationData | None:
        """Get the most recent cached acceleration data (non-blocking).

        This method returns the last received acceleration data (from set_accelerations()
        response) without sending any new requests.

        Returns:
            AccelerationData instance or None if no data received yet.

        Example:
            >>> data = manager.get_current_accelerations()
            >>> if data:
            ...     age = time.time() - data.timestamp
            ...     if age < 0.1:  # Less than 100ms old
            ...         print(f"Fresh accelerations: {data.accelerations}")
        """
        return self._latest_acceleration_data

    def _on_message(self, msg: can.Message) -> None:
        """Handle incoming CAN messages (callback from dispatcher thread).

        Filters for speed and acceleration response messages and updates cache.
        The responses echo the sent data.

        Args:
            msg: CAN message from the bus.

        Note:
            This method executes in the dispatcher's receive thread and must
            return quickly to avoid blocking message reception.
        """
        # Filter: only process messages with correct arbitration ID
        if msg.arbitration_id != self._arbitration_id:
            return

        # Check command byte and process accordingly
        if len(msg.data) < 2:
            return

        if msg.data[0] == self._SPEED_CMD:
            # Parse speed data (skip first byte which is the command)
            speeds = tuple(msg.data[1:])

            # Validate speed count (should be 6 speeds)
            if len(speeds) != self._SPEED_COUNT:
                return

            # Create immutable speed data
            speed_data = SpeedData(speeds=speeds, timestamp=time.time())

            # Dispatch to cache
            self._on_complete_speed_data(speed_data)

        elif msg.data[0] == self._ACCELERATION_CMD:
            # Parse acceleration data (skip first byte which is the command)
            accelerations = tuple(msg.data[1:])

            # Validate acceleration count (should be 6 accelerations)
            if len(accelerations) != self._SPEED_COUNT:
                return

            # Create immutable acceleration data
            acceleration_data = AccelerationData(
                accelerations=accelerations, timestamp=time.time()
            )

            # Dispatch to cache
            self._on_complete_acceleration_data(acceleration_data)

    def _on_complete_speed_data(self, data: SpeedData) -> None:
        """Handle complete speed data by updating cache.

        This method updates the cached latest speed data.

        Args:
            data: Complete speed data to cache.

        Note:
            This method executes in the dispatcher's receive thread.
        """
        # Update cache (atomic reference assignment)
        self._latest_speed_data = data

    def _on_complete_acceleration_data(self, data: AccelerationData) -> None:
        """Handle complete acceleration data by updating cache.

        This method updates the cached latest acceleration data.

        Args:
            data: Complete acceleration data to cache.

        Note:
            This method executes in the dispatcher's receive thread.
        """
        # Update cache (atomic reference assignment)
        self._latest_acceleration_data = data
