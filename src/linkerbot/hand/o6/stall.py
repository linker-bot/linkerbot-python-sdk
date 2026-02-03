"""Stall detection configuration for O6 robotic hand.

This module provides the StallManager class for configuring motor stall
detection parameters.
"""

import threading
from dataclasses import dataclass

import can

from linkerbot.comm import CANMessageDispatcher
from linkerbot.exceptions import TimeoutError, ValidationError


@dataclass
class O6StallThreshold:
    """Motor stall detection threshold for O6 hand (0-1000 range).

    The threshold value represents the current threshold in milliamps (mA)
    for detecting when a motor is stalled.

    Attributes:
        thumb_flex: Thumb flexion motor stall threshold (0-1000 mA)
        thumb_abd: Thumb abduction motor stall threshold (0-1000 mA)
        index: Index finger motor stall threshold (0-1000 mA)
        middle: Middle finger motor stall threshold (0-1000 mA)
        ring: Ring finger motor stall threshold (0-1000 mA)
        pinky: Pinky finger motor stall threshold (0-1000 mA)
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

    def to_raw(self) -> list[int]:
        # Internal: Convert to hardware communication format
        # Formula: raw_value = threshold_ma * 255 / 1000
        return [int(v * 255 / 1000) for v in self.to_list()]

    @classmethod
    def from_list(cls, values: list[float]) -> "O6StallThreshold":
        """Construct from list of floats (0-1000 range).

        Args:
            values: List of 6 float values (0-1000 range)

        Returns:
            O6StallThreshold instance

        Raises:
            ValueError: If list doesn't have exactly 6 elements
        """
        if len(values) != 6:
            raise ValueError(f"Expected 6 values, got {len(values)}")
        for value in values:
            if not isinstance(value, (float, int)):
                raise ValueError(f"Threshold value {value} must be float/int")
            if not 0 <= value <= 1000:
                raise ValueError(f"Threshold value {value} out of range [0, 1000]")
        return cls(
            thumb_flex=values[0],
            thumb_abd=values[1],
            index=values[2],
            middle=values[3],
            ring=values[4],
            pinky=values[5],
        )

    @classmethod
    def from_raw(cls, values: list[int]) -> "O6StallThreshold":
        # Internal: Construct from hardware communication format
        # Formula: threshold_ma = raw_value * 1000 / 255
        if len(values) != 6:
            raise ValueError(f"Expected 6 values, got {len(values)}")
        thresholds = [v * 1000 / 255 for v in values]
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
        """Return number of motors (always 6 for O6)."""
        return 6


@dataclass
class O6StallTime:
    """Motor stall detection time for O6 hand in milliseconds (ms).

    Attributes:
        thumb_flex: Thumb flexion motor stall time in ms (0-2550)
        thumb_abd: Thumb abduction motor stall time in ms (0-2550)
        index: Index finger motor stall time in ms (0-2550)
        middle: Middle finger motor stall time in ms (0-2550)
        ring: Ring finger motor stall time in ms (0-2550)
        pinky: Pinky finger motor stall time in ms (0-2550)
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
    def from_list(cls, values: list[float]) -> "O6StallTime":
        """Construct from list of floats in milliseconds (0-2550 range).

        Args:
            values: List of 6 float values in ms (0-2550 range)

        Returns:
            O6StallTime instance

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
    def from_raw(cls, values: list[int]) -> "O6StallTime":
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
        """Return number of motors (always 6 for O6)."""
        return 6


@dataclass
class O6StallTorque:
    """Motor stall torque limit for O6 hand (0-1000 range).

    The torque value represents the maximum current in milliamps (mA)
    the motor can output when stalled.

    Attributes:
        thumb_flex: Thumb flexion motor stall torque (0-1000 mA)
        thumb_abd: Thumb abduction motor stall torque (0-1000 mA)
        index: Index finger motor stall torque (0-1000 mA)
        middle: Middle finger motor stall torque (0-1000 mA)
        ring: Ring finger motor stall torque (0-1000 mA)
        pinky: Pinky finger motor stall torque (0-1000 mA)
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
    def from_list(cls, values: list[float]) -> "O6StallTorque":
        """Construct from list of floats (0-1000 range).

        Args:
            values: List of 6 float values (0-1000 range)

        Returns:
            O6StallTorque instance

        Raises:
            ValueError: If list doesn't have exactly 6 elements
        """
        if len(values) != 6:
            raise ValueError(f"Expected 6 values, got {len(values)}")
        for value in values:
            if not isinstance(value, (float, int)):
                raise ValueError(f"Torque value {value} must be float/int")
            if not 0 <= value <= 1000:
                raise ValueError(f"Torque value {value} out of range [0, 1000]")
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
        # Formula: raw_value = torque_ma * 255 / 1000
        return [int(v * 255 / 1000) for v in self.to_list()]

    @classmethod
    def from_raw(cls, values: list[int]) -> "O6StallTorque":
        # Internal: Construct from hardware communication format
        # Formula: torque_ma = raw_value * 1000 / 255
        if len(values) != 6:
            raise ValueError(f"Expected 6 values, got {len(values)}")
        torques = [v * 1000 / 255 for v in values]
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
        """Return number of motors (always 6 for O6)."""
        return 6


class StallManager:
    """Manager for motor stall detection configuration.

    This class handles configuration of stall detection parameters including:
    - Stall threshold: Current threshold for detecting stall (0xC5)
    - Stall time: Time threshold for detecting stall condition (0xC6)
    - Stall torque: Maximum torque output when stalled (0xC7)

    Each parameter supports both setting and getting operations.
    Changes require save_parameters() and device restart to take effect.
    """

    _THRESHOLD_CMD = 0xC5
    _TIME_CMD = 0xC6
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

        # Blocking read support
        self._threshold_waiters: list[tuple[threading.Event, dict]] = []
        self._threshold_lock = threading.Lock()
        self._time_waiters: list[tuple[threading.Event, dict]] = []
        self._time_lock = threading.Lock()
        self._torque_waiters: list[tuple[threading.Event, dict]] = []
        self._torque_lock = threading.Lock()

    def set_stall_threshold(self, threshold: O6StallThreshold | list[float]) -> None:
        """Set motor stall detection current thresholds.

        This method configures the current threshold for detecting when a motor
        is stalled. The threshold represents the current level in milliamps (mA)
        that indicates a stall condition.

        Note: Changes require save_parameters() and device restart to take effect.

        Args:
            threshold: O6StallThreshold instance or list of 6 threshold values (0-1000 mA).

        Raises:
            ValidationError: If threshold count is not 6 or values are out of range.

        Example:
            >>> manager = StallManager(arbitration_id, dispatcher)
            >>> # Using O6StallThreshold instance
            >>> manager.set_stall_threshold(O6StallThreshold(thumb_flex=500.0, thumb_abd=500.0,
            ...                                              index=500.0, middle=500.0, ring=500.0, pinky=500.0))
            >>> # Using list (values in milliamps)
            >>> manager.set_stall_threshold([500.0, 500.0, 500.0, 500.0, 500.0, 500.0])
            >>> # Save and restart to apply
            >>> manager.save_parameters()
        """
        if isinstance(threshold, O6StallThreshold):
            raw_threshold = threshold.to_raw()
        elif isinstance(threshold, list):
            raw_threshold = O6StallThreshold.from_list(threshold).to_raw()

        # Build and send message
        data = [self._THRESHOLD_CMD, *raw_threshold]
        msg = can.Message(
            arbitration_id=self._arbitration_id,
            data=data,
            is_extended_id=False,
        )
        self._dispatcher.send(msg)

    def get_stall_threshold(self, timeout_ms: float = 100) -> O6StallThreshold:
        """Read current stall detection thresholds from device.

        Args:
            timeout_ms: Maximum time to wait in milliseconds (default: 100).

        Returns:
            O6StallThreshold instance containing current threshold values.

        Raises:
            TimeoutError: If no response is received within timeout.
            ValidationError: If timeout_ms is not positive.

        Example:
            >>> manager = StallManager(arbitration_id, dispatcher)
            >>> threshold = manager.get_stall_threshold()
            >>> print(f"Thumb flex threshold: {threshold.thumb_flex} mA")
        """
        if timeout_ms <= 0:
            raise ValidationError("timeout_ms must be positive")

        event = threading.Event()
        result_holder: dict[str, O6StallThreshold | None] = {"data": None}

        with self._threshold_lock:
            self._threshold_waiters.append((event, result_holder))

        # Send read request (just the command byte)
        msg = can.Message(
            arbitration_id=self._arbitration_id,
            data=[self._THRESHOLD_CMD],
            is_extended_id=False,
        )
        self._dispatcher.send(msg)

        if event.wait(timeout_ms / 1000.0):
            if result_holder["data"] is None:
                raise TimeoutError(f"No data received within {timeout_ms}ms")
            return result_holder["data"]
        else:
            with self._threshold_lock:
                if (event, result_holder) in self._threshold_waiters:
                    self._threshold_waiters.remove((event, result_holder))
            raise TimeoutError(f"No threshold data received within {timeout_ms}ms")

    def set_stall_time(self, time: O6StallTime | list[float]) -> None:
        """Set motor stall detection time thresholds.

        This method configures the time threshold for detecting when a motor
        is stalled. The time represents how long the motor must be in a stall
        condition before it is detected.

        Note: Changes require save_parameters() and device restart to take effect.

        Args:
            time: O6StallTime instance or list of 6 time values in milliseconds (0-2550 ms).

        Raises:
            ValidationError: If time count is not 6 or values are out of range.

        Example:
            >>> manager = StallManager(arbitration_id, dispatcher)
            >>> # Using O6StallTime instance
            >>> manager.set_stall_time(O6StallTime(thumb_flex=500.0, thumb_abd=500.0,
            ...                                     index=500.0, middle=500.0, ring=500.0, pinky=500.0))
            >>> # Using list (values in milliseconds)
            >>> manager.set_stall_time([500.0, 500.0, 500.0, 500.0, 500.0, 500.0])
            >>> # Save and restart to apply
            >>> manager.save_parameters()
        """
        if isinstance(time, O6StallTime):
            raw_time = time.to_raw()
        elif isinstance(time, list):
            raw_time = O6StallTime.from_list(time).to_raw()

        # Build and send message
        data = [self._TIME_CMD, *raw_time]
        msg = can.Message(
            arbitration_id=self._arbitration_id,
            data=data,
            is_extended_id=False,
        )
        self._dispatcher.send(msg)

    def get_stall_time(self, timeout_ms: float = 100) -> O6StallTime:
        """Read current stall detection times from device.

        Args:
            timeout_ms: Maximum time to wait in milliseconds (default: 100).

        Returns:
            O6StallTime instance containing current time values.

        Raises:
            TimeoutError: If no response is received within timeout.
            ValidationError: If timeout_ms is not positive.

        Example:
            >>> manager = StallManager(arbitration_id, dispatcher)
            >>> stall_time = manager.get_stall_time()
            >>> print(f"Thumb flex stall time: {stall_time.thumb_flex} ms")
        """
        if timeout_ms <= 0:
            raise ValidationError("timeout_ms must be positive")

        event = threading.Event()
        result_holder: dict[str, O6StallTime | None] = {"data": None}

        with self._time_lock:
            self._time_waiters.append((event, result_holder))

        # Send read request (just the command byte)
        msg = can.Message(
            arbitration_id=self._arbitration_id,
            data=[self._TIME_CMD],
            is_extended_id=False,
        )
        self._dispatcher.send(msg)

        if event.wait(timeout_ms / 1000.0):
            if result_holder["data"] is None:
                raise TimeoutError(f"No data received within {timeout_ms}ms")
            return result_holder["data"]
        else:
            with self._time_lock:
                if (event, result_holder) in self._time_waiters:
                    self._time_waiters.remove((event, result_holder))
            raise TimeoutError(f"No time data received within {timeout_ms}ms")

    def set_stall_torque(self, torque: O6StallTorque | list[float]) -> None:
        """Set motor stall torque limits.

        This method configures the maximum current output in milliamps (mA)
        that a motor can produce when in a stalled condition. This limits
        the torque output to prevent damage.

        Note: Changes require save_parameters() and device restart to take effect.

        Args:
            torque: O6StallTorque instance or list of 6 torque values (0-1000 mA).

        Raises:
            ValidationError: If torque count is not 6 or values are out of range.

        Example:
            >>> manager = StallManager(arbitration_id, dispatcher)
            >>> # Using O6StallTorque instance
            >>> manager.set_stall_torque(O6StallTorque(thumb_flex=700.0, thumb_abd=700.0,
            ...                                        index=700.0, middle=700.0, ring=700.0, pinky=700.0))
            >>> # Using list (values in milliamps)
            >>> manager.set_stall_torque([700.0, 700.0, 700.0, 700.0, 700.0, 700.0])
            >>> # Save and restart to apply
            >>> manager.save_parameters()
        """
        if isinstance(torque, O6StallTorque):
            raw_torque = torque.to_raw()
        elif isinstance(torque, list):
            raw_torque = O6StallTorque.from_list(torque).to_raw()

        # Build and send message
        data = [self._TORQUE_CMD, *raw_torque]
        msg = can.Message(
            arbitration_id=self._arbitration_id,
            data=data,
            is_extended_id=False,
        )
        self._dispatcher.send(msg)

    def get_stall_torque(self, timeout_ms: float = 100) -> O6StallTorque:
        """Read current stall torque limits from device.

        Args:
            timeout_ms: Maximum time to wait in milliseconds (default: 100).

        Returns:
            O6StallTorque instance containing current torque values.

        Raises:
            TimeoutError: If no response is received within timeout.
            ValidationError: If timeout_ms is not positive.

        Example:
            >>> manager = StallManager(arbitration_id, dispatcher)
            >>> stall_torque = manager.get_stall_torque()
            >>> print(f"Thumb flex stall torque: {stall_torque.thumb_flex} mA")
        """
        if timeout_ms <= 0:
            raise ValidationError("timeout_ms must be positive")

        event = threading.Event()
        result_holder: dict[str, O6StallTorque | None] = {"data": None}

        with self._torque_lock:
            self._torque_waiters.append((event, result_holder))

        # Send read request (just the command byte)
        msg = can.Message(
            arbitration_id=self._arbitration_id,
            data=[self._TORQUE_CMD],
            is_extended_id=False,
        )
        self._dispatcher.send(msg)

        if event.wait(timeout_ms / 1000.0):
            if result_holder["data"] is None:
                raise TimeoutError(f"No data received within {timeout_ms}ms")
            return result_holder["data"]
        else:
            with self._torque_lock:
                if (event, result_holder) in self._torque_waiters:
                    self._torque_waiters.remove((event, result_holder))
            raise TimeoutError(f"No torque data received within {timeout_ms}ms")

    def save_parameters(self, timeout_ms: float = 200) -> None:
        """Save current stall detection parameters to non-volatile memory.

        This method sends a save command to persist the current stall detection
        configuration (threshold, time, and torque) so they are retained after
        power cycling.

        Note: Device restart is required for saved parameters to take effect.

        Args:
            timeout_ms: Maximum time to wait for save confirmation in milliseconds (default: 200).

        Raises:
            TimeoutError: If no confirmation is received within timeout.
            ValidationError: If timeout_ms is not positive.

        Example:
            >>> manager = StallManager(arbitration_id, dispatcher)
            >>> # Configure parameters
            >>> manager.set_stall_threshold([500.0, 500.0, 500.0, 500.0, 500.0, 500.0])
            >>> manager.set_stall_time([500.0, 500.0, 500.0, 500.0, 500.0, 500.0])
            >>> manager.set_stall_torque([700.0, 700.0, 700.0, 700.0, 700.0, 700.0])
            >>> # Save to non-volatile memory
            >>> try:
            ...     manager.save_parameters()
            ...     print("Parameters saved successfully - restart device to apply")
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

        if len(msg.data) < 1:
            return

        cmd = msg.data[0]

        # Handle save confirmation
        if cmd == self._SAVE_CMD and len(msg.data) >= 2:
            if msg.data[1] == 0x01:
                with self._save_lock:
                    for event, result_holder in self._save_waiters:
                        result_holder["success"] = True
                        event.set()
                    self._save_waiters.clear()
            return

        # Handle threshold response
        if cmd == self._THRESHOLD_CMD and len(msg.data) >= 7:
            raw_values = list(msg.data[1:7])
            threshold = O6StallThreshold.from_raw(raw_values)
            with self._threshold_lock:
                for event, result_holder in self._threshold_waiters:
                    result_holder["data"] = threshold
                    event.set()
                self._threshold_waiters.clear()
            return

        # Handle time response
        if cmd == self._TIME_CMD and len(msg.data) >= 7:
            raw_values = list(msg.data[1:7])
            stall_time = O6StallTime.from_raw(raw_values)
            with self._time_lock:
                for event, result_holder in self._time_waiters:
                    result_holder["data"] = stall_time
                    event.set()
                self._time_waiters.clear()
            return

        # Handle torque response
        if cmd == self._TORQUE_CMD and len(msg.data) >= 7:
            raw_values = list(msg.data[1:7])
            torque = O6StallTorque.from_raw(raw_values)
            with self._torque_lock:
                for event, result_holder in self._torque_waiters:
                    result_holder["data"] = torque
                    event.set()
                self._torque_waiters.clear()
            return
