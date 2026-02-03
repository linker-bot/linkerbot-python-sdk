"""Stall detection configuration for L6 robotic hand.

This module provides the StallManager class for configuring motor stall
detection parameters.
"""

import threading
from dataclasses import dataclass

import can

from linkerbot.comm import CANMessageDispatcher
from linkerbot.exceptions import TimeoutError, ValidationError


@dataclass
class L6StallTime:
    """Motor stall detection time for L6 hand in milliseconds (ms).

    Attributes:
        thumb_flex: Thumb flexion motor stall time in ms (10-2550)
        thumb_abd: Thumb abduction motor stall time in ms (10-2550)
        index: Index finger motor stall time in ms (10-2550)
        middle: Middle finger motor stall time in ms (10-2550)
        ring: Ring finger motor stall time in ms (10-2550)
        pinky: Pinky finger motor stall time in ms (10-2550)
    """

    thumb_flex: float
    thumb_abd: float
    index: float
    middle: float
    ring: float
    pinky: float

    def to_list(self) -> list[float]:
        """Convert to list of floats in joint order.

        Returns:
            List of 6 stall times in ms [thumb_flex, thumb_abd, index, middle, ring, pinky]
        """
        return [
            self.thumb_flex,
            self.thumb_abd,
            self.index,
            self.middle,
            self.ring,
            self.pinky,
        ]

    @classmethod
    def from_list(cls, values: list[float]) -> "L6StallTime":
        """Construct from list of floats in milliseconds (10-2550 range).

        Args:
            values: List of 6 float values in ms (10-2550 range)

        Returns:
            L6StallTime instance

        Raises:
            ValueError: If list doesn't have exactly 6 elements
        """
        if len(values) != 6:
            raise ValueError(f"Expected 6 values, got {len(values)}")
        for value in values:
            if not isinstance(value, (float, int)):
                raise ValueError(f"Stall time value {value} must be float/int")
            if not 0 <= value <= 2550:
                raise ValueError(f"Stall time value {value} out of range [0, 2550]")
        return cls(
            thumb_flex=values[0],
            thumb_abd=values[1],
            index=values[2],
            middle=values[3],
            ring=values[4],
            pinky=values[5],
        )

    def to_raw(self) -> list[int]:
        # Internal: Convert to hardware communication format (time_ms / 10)
        return [int(v / 10) for v in self.to_list()]

    @classmethod
    def from_raw(cls, values: list[int]) -> "L6StallTime":
        # Internal: Construct from hardware communication format
        if len(values) != 6:
            raise ValueError(f"Expected 6 values, got {len(values)}")
        times_ms = [float(v * 10) for v in values]
        return cls.from_list(times_ms)

    def __getitem__(self, index: int) -> float:
        """Support indexing: stall_times[0] returns thumb_flex.

        Args:
            index: Joint index (0-5)

        Returns:
            Stall time value

        Raises:
            IndexError: If index is out of range
        """
        return self.to_list()[index]

    def __len__(self) -> int:
        """Return number of motors (always 6 for L6)."""
        return 6


@dataclass
class L6StallThreshold:
    """Motor stall detection threshold for L6 hand (0-1400 range).

    The threshold value represents the current threshold in milliamps (mA)
    for detecting when a motor is stalled.

    Attributes:
        thumb_flex: Thumb flexion motor stall threshold (0-1400 mA)
        thumb_abd: Thumb abduction motor stall threshold (0-1400 mA)
        index: Index finger motor stall threshold (0-1400 mA)
        middle: Middle finger motor stall threshold (0-1400 mA)
        ring: Ring finger motor stall threshold (0-1400 mA)
        pinky: Pinky finger motor stall threshold (0-1400 mA)
    """

    thumb_flex: float
    thumb_abd: float
    index: float
    middle: float
    ring: float
    pinky: float

    def to_list(self) -> list[float]:
        """Convert to list of floats in joint order.

        Returns:
            List of 6 thresholds [thumb_flex, thumb_abd, index, middle, ring, pinky]
        """
        return [
            self.thumb_flex,
            self.thumb_abd,
            self.index,
            self.middle,
            self.ring,
            self.pinky,
        ]

    @classmethod
    def from_list(cls, values: list[float]) -> "L6StallThreshold":
        """Construct from list of floats (0-1400 range).

        Args:
            values: List of 6 float values (0-1400 range)

        Returns:
            L6StallThreshold instance

        Raises:
            ValueError: If list doesn't have exactly 6 elements
        """
        if len(values) != 6:
            raise ValueError(f"Expected 6 values, got {len(values)}")
        for value in values:
            if not isinstance(value, (float, int)):
                raise ValueError(f"Threshold value {value} must be float/int")
            if not 0 <= value <= 1400:
                raise ValueError(f"Threshold value {value} out of range [0, 1400]")
        return cls(
            thumb_flex=values[0],
            thumb_abd=values[1],
            index=values[2],
            middle=values[3],
            ring=values[4],
            pinky=values[5],
        )

    def to_raw(self) -> list[int]:
        # Internal: Convert to hardware communication format
        return [int(v * 255 / 1400) for v in self.to_list()]

    @classmethod
    def from_raw(cls, values: list[int]) -> "L6StallThreshold":
        # Internal: Construct from hardware communication format
        if len(values) != 6:
            raise ValueError(f"Expected 6 values, got {len(values)}")
        thresholds = [v * 1400 / 255 for v in values]
        return cls.from_list(thresholds)

    def __getitem__(self, index: int) -> float:
        """Support indexing: thresholds[0] returns thumb_flex.

        Args:
            index: Joint index (0-5)

        Returns:
            Threshold value

        Raises:
            IndexError: If index is out of range
        """
        return self.to_list()[index]

    def __len__(self) -> int:
        """Return number of motors (always 6 for L6)."""
        return 6


@dataclass
class L6StallTorque:
    """Motor stall torque limit for L6 hand (0-1400 range).

    The torque value represents the maximum current in milliamps (mA)
    the motor can output when stalled.

    Attributes:
        thumb_flex: Thumb flexion motor stall torque (0-1400 mA)
        thumb_abd: Thumb abduction motor stall torque (0-1400 mA)
        index: Index finger motor stall torque (0-1400 mA)
        middle: Middle finger motor stall torque (0-1400 mA)
        ring: Ring finger motor stall torque (0-1400 mA)
        pinky: Pinky finger motor stall torque (0-1400 mA)
    """

    thumb_flex: float
    thumb_abd: float
    index: float
    middle: float
    ring: float
    pinky: float

    def to_list(self) -> list[float]:
        """Convert to list of floats in joint order.

        Returns:
            List of 6 torques [thumb_flex, thumb_abd, index, middle, ring, pinky]
        """
        return [
            self.thumb_flex,
            self.thumb_abd,
            self.index,
            self.middle,
            self.ring,
            self.pinky,
        ]

    @classmethod
    def from_list(cls, values: list[float]) -> "L6StallTorque":
        """Construct from list of floats (0-1400 range).

        Args:
            values: List of 6 float values (0-1400 range)

        Returns:
            L6StallTorque instance

        Raises:
            ValueError: If list doesn't have exactly 6 elements
        """
        if len(values) != 6:
            raise ValueError(f"Expected 6 values, got {len(values)}")
        for value in values:
            if not isinstance(value, (float, int)):
                raise ValueError(f"Torque value {value} must be float/int")
            if not 0 <= value <= 1400:
                raise ValueError(f"Torque value {value} out of range [0, 1400]")
        return cls(
            thumb_flex=values[0],
            thumb_abd=values[1],
            index=values[2],
            middle=values[3],
            ring=values[4],
            pinky=values[5],
        )

    def to_raw(self) -> list[int]:
        # Internal: Convert to hardware communication format
        return [int(v * 255 / 1400) for v in self.to_list()]

    @classmethod
    def from_raw(cls, values: list[int]) -> "L6StallTorque":
        # Internal: Construct from hardware communication format
        if len(values) != 6:
            raise ValueError(f"Expected 6 values, got {len(values)}")
        torques = [v * 1400 / 255 for v in values]
        return cls.from_list(torques)

    def __getitem__(self, index: int) -> float:
        """Support indexing: torques[0] returns thumb_flex.

        Args:
            index: Joint index (0-5)

        Returns:
            Torque value

        Raises:
            IndexError: If index is out of range
        """
        return self.to_list()[index]

    def __len__(self) -> int:
        """Return number of motors (always 6 for L6)."""
        return 6


class StallManager:
    """Manager for motor stall detection configuration.

    This class handles configuration of stall detection parameters including:
    - Stall time: Time threshold for detecting stall condition
    - Stall threshold: Current threshold for detecting stall
    - Stall torque: Maximum torque output when stalled
    """

    _TIME_CMD = 0xC5
    _THRESHOLD_CMD = 0xC6
    _TORQUE_CMD = 0xC7
    _SAVE_CMD = 0xCF
    _PARAM_COUNT = 6

    def __init__(self, arbitration_id: int, dispatcher: CANMessageDispatcher) -> None:
        """Initialize the stall manager.

        Args:
            arbitration_id: Arbitration ID for stall configuration.
            dispatcher: Message dispatcher for communication.
        """
        self._arbitration_id = arbitration_id
        self._dispatcher = dispatcher
        self._dispatcher.subscribe(self._on_message)

        # Save operation support
        self._save_waiters: list[tuple[threading.Event, dict]] = []
        self._save_lock = threading.Lock()

    def set_stall_time(self, time: L6StallTime | list[float]) -> None:
        """Set motor stall detection time thresholds.

        This method configures the time threshold for detecting when a motor
        is stalled. The time represents how long the motor must be in a stall
        condition before it is detected. The configuration is automatically
        saved to non-volatile memory.

        Args:
            time: L6StallTime instance or list of 6 time values in milliseconds (10-2550 ms).
                  Setting 0 disables the stall detection for that motor.

        Raises:
            ValidationError: If time count is not 6 or values are out of range.

        Example:
            >>> manager = StallManager(arbitration_id, dispatcher)
            >>> # Using L6StallTime instance
            >>> manager.set_stall_time(L6StallTime(thumb_flex=500.0, thumb_abd=500.0,
            ...                                     index=500.0, middle=500.0, ring=500.0, pinky=500.0))
            >>> # Using list (values in milliseconds)
            >>> manager.set_stall_time([500.0, 500.0, 500.0, 500.0, 500.0, 500.0])
        """
        if isinstance(time, L6StallTime):
            raw_time = time.to_raw()
        elif isinstance(time, list):
            raw_time = L6StallTime.from_list(time).to_raw()

        # Build and send message
        data = [self._TIME_CMD, *raw_time]
        msg = can.Message(
            arbitration_id=self._arbitration_id,
            data=data,
            is_extended_id=False,
        )
        self._dispatcher.send(msg)
        self._save_parameters()

    def set_stall_threshold(self, threshold: L6StallThreshold | list[float]) -> None:
        """Set motor stall detection current thresholds.

        This method configures the current threshold for detecting when a motor
        is stalled. The threshold represents the current level in milliamps (mA)
        that indicates a stall condition. The configuration is automatically
        saved to non-volatile memory.

        Args:
            threshold: L6StallThreshold instance or list of 6 threshold values (0-1400 mA).

        Raises:
            ValidationError: If threshold count is not 6 or values are out of range.

        Example:
            >>> manager = StallManager(arbitration_id, dispatcher)
            >>> # Using L6StallThreshold instance (default is 500 mA)
            >>> manager.set_stall_threshold(L6StallThreshold(thumb_flex=500.0, thumb_abd=500.0,
            ...                                              index=500.0, middle=500.0, ring=500.0, pinky=500.0))
            >>> # Using list (values in milliamps)
            >>> manager.set_stall_threshold([500.0, 500.0, 500.0, 500.0, 500.0, 500.0])
        """
        if isinstance(threshold, L6StallThreshold):
            raw_threshold = threshold.to_raw()
        elif isinstance(threshold, list):
            raw_threshold = L6StallThreshold.from_list(threshold).to_raw()

        # Build and send message
        data = [self._THRESHOLD_CMD, *raw_threshold]
        msg = can.Message(
            arbitration_id=self._arbitration_id,
            data=data,
            is_extended_id=False,
        )
        self._dispatcher.send(msg)
        self._save_parameters()

    def set_stall_torque(self, torque: L6StallTorque | list[float]) -> None:
        """Set motor stall torque limits.

        This method configures the maximum current output in milliamps (mA)
        that a motor can produce when in a stalled condition. This limits
        the torque output to prevent damage. The configuration is automatically
        saved to non-volatile memory.

        Args:
            torque: L6StallTorque instance or list of 6 torque values (0-1400 mA).

        Raises:
            ValidationError: If torque count is not 6 or values are out of range.

        Example:
            >>> manager = StallManager(arbitration_id, dispatcher)
            >>> # Using L6StallTorque instance (default is 700 mA)
            >>> manager.set_stall_torque(L6StallTorque(thumb_flex=700.0, thumb_abd=700.0,
            ...                                        index=700.0, middle=700.0, ring=700.0, pinky=700.0))
            >>> # Using list (values in milliamps)
            >>> manager.set_stall_torque([700.0, 700.0, 700.0, 700.0, 700.0, 700.0])
        """
        if isinstance(torque, L6StallTorque):
            raw_torque = torque.to_raw()
        elif isinstance(torque, list):
            raw_torque = L6StallTorque.from_list(torque).to_raw()

        # Build and send message
        data = [self._TORQUE_CMD, *raw_torque]
        msg = can.Message(
            arbitration_id=self._arbitration_id,
            data=data,
            is_extended_id=False,
        )
        self._dispatcher.send(msg)
        self._save_parameters()

    def _save_parameters(self, timeout_ms: float = 200) -> None:
        """Save current stall detection parameters to non-volatile memory.

        This method sends a save command to persist the current stall detection
        configuration (time, threshold, and torque) so they are retained after
        power cycling.

        Args:
            timeout_ms: Maximum time to wait for save confirmation in milliseconds (default: 200).

        Raises:
            TimeoutError: If no confirmation is received within timeout.
            ValidationError: If timeout_ms is not positive.

        Example:
            >>> manager = StallManager(arbitration_id, dispatcher)
            >>> # Configure parameters
            >>> manager.set_stall_time([500.0, 500.0, 500.0, 500.0, 500.0, 500.0])
            >>> manager.set_stall_threshold([500.0, 500.0, 500.0, 500.0, 500.0, 500.0])
            >>> manager.set_stall_torque([700.0, 700.0, 700.0, 700.0, 700.0, 700.0])
            >>> # Save to non-volatile memory
            >>> try:
            ...     manager.save_parameters()
            ...     print("Parameters saved successfully")
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

    def _on_message(self, msg: can.Message) -> None:
        # Filter: only process messages with correct arbitration ID
        if msg.arbitration_id != self._arbitration_id:
            return

        # Filter: only process save confirmation messages
        if len(msg.data) >= 2 and msg.data[0] == self._SAVE_CMD:
            # Check for success response: 0xCF 0x01
            if msg.data[1] == 0x01:
                # Wake up all save waiters
                with self._save_lock:
                    for event, result_holder in self._save_waiters:
                        result_holder["success"] = True
                        event.set()
                    self._save_waiters.clear()
