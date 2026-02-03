"""Joint limit compensation configuration for L6 robotic hand.

This module provides the LimitCompensationManager class for configuring
joint limit compensation values via CAN bus communication.
"""

import threading
import time
from dataclasses import dataclass

import can

from linkerbot.comm import CANMessageDispatcher
from linkerbot.exceptions import TimeoutError, ValidationError


@dataclass
class L6LimitCompensation:
    """Joint limit compensation values for L6 hand (0-255 range).

    Each compensation value is added to the joint's maximum limit (1700).
    For example, a compensation value of 255 increases the max limit to 1955.

    Attributes:
        thumb_flex: Thumb flexion joint compensation (0-255)
        thumb_abd: Thumb abduction joint compensation (0-255)
        index: Index finger flexion joint compensation (0-255)
        middle: Middle finger flexion joint compensation (0-255)
        ring: Ring finger flexion joint compensation (0-255)
        pinky: Pinky finger flexion joint compensation (0-255)
    """

    thumb_flex: int
    thumb_abd: int
    index: int
    middle: int
    ring: int
    pinky: int

    def to_list(self) -> list[int]:
        """Convert to list of integers in joint order.

        Returns:
            List of 6 joint compensation values [thumb_flex, thumb_abd, index, middle, ring, pinky]
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
    def from_list(cls, values: list[int]) -> "L6LimitCompensation":
        """Construct from list of integers (0-255 range).

        Args:
            values: List of 6 integer values in 0-255 range

        Returns:
            L6LimitCompensation instance

        Raises:
            ValueError: If list doesn't have exactly 6 elements
        """
        if len(values) != 6:
            raise ValueError(f"Expected 6 values, got {len(values)}")
        return cls(
            thumb_flex=values[0],
            thumb_abd=values[1],
            index=values[2],
            middle=values[3],
            ring=values[4],
            pinky=values[5],
        )

    def __getitem__(self, index: int) -> int:
        """Support indexing: compensation[0] returns thumb_flex.

        Args:
            index: Joint index (0-5)

        Returns:
            Joint compensation value

        Raises:
            IndexError: If index is out of range
        """
        return self.to_list()[index]

    def __len__(self) -> int:
        """Return number of joints (always 6 for L6)."""
        return 6


@dataclass(frozen=True)
class LimitCompensationData:
    """Immutable limit compensation data container.

    Attributes:
        compensation: L6LimitCompensation instance containing joint compensation values (0-255 range).
        timestamp: Unix timestamp when the data was received.
    """

    compensation: L6LimitCompensation
    timestamp: float


class LimitCompensationManager:
    """Manager for joint limit compensation configuration.

    This class provides methods to configure and read joint limit compensation values.
    Compensation values are added to each joint's maximum limit (base limit: 1700).

    Provides three access modes:
    1. Set compensation: set_limit_compensation() - configure joint limits (requires password)
    2. Blocking read: get_limit_compensation_blocking() - request and wait for values
    3. Cache read: get_current_limit_compensation() - non-blocking read of cached values
    """

    _CMD = 0x38
    _PASSWORD_CMD = 0xCB
    _JOINT_COUNT = 6

    def __init__(self, arbitration_id: int, dispatcher: CANMessageDispatcher) -> None:
        """Initialize the limit compensation manager.

        Args:
            arbitration_id: CAN arbitration ID for limit compensation configuration.
            dispatcher: CAN message dispatcher to use for communication.
        """
        self._arbitration_id = arbitration_id
        self._dispatcher = dispatcher
        self._dispatcher.subscribe(self._on_message)

        # Latest compensation data cache
        self._latest_data: LimitCompensationData | None = None

        # Blocking mode support
        self._blocking_waiters: list[tuple[threading.Event, dict]] = []
        self._waiters_lock = threading.Lock()

        # Password verification support
        self._password_waiters: list[tuple[threading.Event, dict]] = []
        self._password_lock = threading.Lock()

    def set_limit_compensation(
        self,
        compensation: L6LimitCompensation | list[int],
        password: list[int],
        timeout_ms: float = 200,
    ) -> None:
        """Set joint limit compensation values with password authentication.

        This method sends 6 compensation values to the hand. Password verification
        is required before the compensation values can be modified. The hand will
        respond with the current compensation values, which are automatically cached
        and can be retrieved via get_current_limit_compensation().

        Args:
            compensation: L6LimitCompensation instance or list of 6 compensation values (range 0-255 each).
            password: 6-byte password list for authentication (e.g., [0x06, 0x05, 0x04, 0x03, 0x02, 0x01]).
            timeout_ms: Maximum time to wait for password verification in milliseconds (default: 200).

        Raises:
            ValidationError: If compensation count is not 6, values are out of range,
                password length is not 6, or timeout_ms is not positive.
            TimeoutError: If password verification fails or times out.

        Example:
            >>> manager = LimitCompensationManager(arbitration_id, dispatcher)
            >>> # Using L6LimitCompensation instance
            >>> manager.set_limit_compensation(
            ...     L6LimitCompensation(
            ...         thumb_flex=50, thumb_abd=30, index=60, middle=60, ring=60, pinky=60
            ...     ),
            ...     password=[0x06, 0x05, 0x04, 0x03, 0x02, 0x01]
            ... )
            >>> # Using list
            >>> manager.set_limit_compensation(
            ...     [50, 30, 60, 60, 60, 60],
            ...     password=[0x06, 0x05, 0x04, 0x03, 0x02, 0x01]
            ... )
            >>> time.sleep(0.1)  # Wait for response
            >>> current = manager.get_current_limit_compensation()
            >>> if current:
            ...     print(f"Current compensation: {current.compensation.thumb_flex}")
        """
        if timeout_ms <= 0:
            raise ValidationError("timeout_ms must be positive")

        if len(password) != 6:
            raise ValidationError(f"Password must be 6 bytes, got {len(password)}")

        # Verify password first
        self._verify_password(password, timeout_ms)
        if isinstance(compensation, L6LimitCompensation):
            comp_values = compensation.to_list()
        elif isinstance(compensation, list):
            # Validate input
            if len(compensation) != self._JOINT_COUNT:
                raise ValidationError(
                    f"Expected {self._JOINT_COUNT} compensation values, got {len(compensation)}"
                )
            # Validate compensation values (0-255 range)
            for i, value in enumerate(compensation):
                if not isinstance(value, int):
                    raise ValidationError(
                        f"Compensation {i} must be int, got {type(value)}"
                    )
                if not 0 <= value <= 255:
                    raise ValidationError(
                        f"Compensation {i} value {value} out of range [0, 255]"
                    )
            comp_values = compensation

        # Build and send message
        data = [self._CMD, *comp_values]
        msg = can.Message(
            arbitration_id=self._arbitration_id,
            data=data,
            is_extended_id=False,
        )
        self._dispatcher.send(msg)

    def get_limit_compensation_blocking(
        self, timeout_ms: float = 100
    ) -> LimitCompensationData:
        """Request and wait for current joint limit compensation values (blocking).

        This method sends a read request and blocks until compensation values
        are received or the timeout expires.

        Args:
            timeout_ms: Maximum time to wait in milliseconds (default: 100).

        Returns:
            LimitCompensationData instance containing compensation values and timestamp.

        Raises:
            TimeoutError: If no response is received within timeout.
            ValidationError: If timeout_ms is not positive.

        Example:
            >>> manager = LimitCompensationManager(arbitration_id, dispatcher)
            >>> try:
            ...     data = manager.get_limit_compensation_blocking(timeout_ms=500)
            ...     print(f"Current compensation: {data.compensation}")
            ... except TimeoutError:
            ...     print("Request timed out")
        """
        if timeout_ms <= 0:
            raise ValidationError("timeout_ms must be positive")

        event = threading.Event()
        result_holder: dict[str, LimitCompensationData | None] = {"data": None}

        # Register this waiter
        with self._waiters_lock:
            self._blocking_waiters.append((event, result_holder))

        # Send read request (single byte command)
        msg = can.Message(
            arbitration_id=self._arbitration_id,
            data=[self._CMD],
            is_extended_id=False,
        )
        self._dispatcher.send(msg)

        # Wait for data or timeout
        if event.wait(timeout_ms / 1000.0):
            if result_holder["data"] is None:
                raise TimeoutError(f"No data received within {timeout_ms}ms")
            return result_holder["data"]
        else:
            # Timeout - remove ourselves from waiters list
            with self._waiters_lock:
                if (event, result_holder) in self._blocking_waiters:
                    self._blocking_waiters.remove((event, result_holder))
            raise TimeoutError(
                f"No limit compensation data received within {timeout_ms}ms"
            )

    def get_current_limit_compensation(self) -> LimitCompensationData | None:
        """Get the most recent cached limit compensation data (non-blocking).

        This method returns the last received compensation data (either from
        set_limit_compensation() response or get_limit_compensation_blocking() response)
        without sending any new requests.

        Returns:
            LimitCompensationData instance or None if no data received yet.

        Example:
            >>> data = manager.get_current_limit_compensation()
            >>> if data:
            ...     age = time.time() - data.timestamp
            ...     if age < 0.1:  # Less than 100ms old
            ...         print(f"Fresh compensation: {data.compensation}")
        """
        return self._latest_data

    def _verify_password(self, password: list[int], timeout_ms: float) -> None:
        """Verify password before modifying compensation values."""
        event = threading.Event()
        result_holder: dict[str, bool] = {"success": False}

        with self._password_lock:
            self._password_waiters.append((event, result_holder))

        # Send password
        data = [self._PASSWORD_CMD, *password]
        msg = can.Message(
            arbitration_id=self._arbitration_id,
            data=data,
            is_extended_id=False,
        )
        self._dispatcher.send(msg)

        # Wait for verification
        if event.wait(timeout_ms / 1000.0):
            if not result_holder["success"]:
                raise TimeoutError("Password verification failed")
        else:
            with self._password_lock:
                if (event, result_holder) in self._password_waiters:
                    self._password_waiters.remove((event, result_holder))
            raise TimeoutError(f"Password verification timed out after {timeout_ms}ms")

    def _on_message(self, msg: can.Message) -> None:
        # Internal callback
        if msg.arbitration_id != self._arbitration_id:
            return

        if len(msg.data) < 1:
            return

        cmd = msg.data[0]

        # Handle password verification response
        if cmd == self._PASSWORD_CMD:
            success = len(msg.data) >= 7
            with self._password_lock:
                for event, result_holder in self._password_waiters:
                    result_holder["success"] = success
                    event.set()
                self._password_waiters.clear()
            return

        # Handle limit compensation response (start with 0x38)
        if cmd != self._CMD or len(msg.data) < 2:
            return

        # Parse compensation data (skip first byte which is the command)
        comp_values = list(msg.data[1:])

        # Validate compensation count (should be 6 values)
        if len(comp_values) != self._JOINT_COUNT:
            return

        compensation = L6LimitCompensation.from_list(comp_values)
        comp_data = LimitCompensationData(
            compensation=compensation, timestamp=time.time()
        )
        self._on_complete_data(comp_data)

    def _on_complete_data(self, data: LimitCompensationData) -> None:
        # Internal: Handle complete compensation data
        # Update cache
        self._latest_data = data

        # Wake up all blocking waiters
        with self._waiters_lock:
            for event, result_holder in self._blocking_waiters:
                result_holder["data"] = data
                event.set()
            self._blocking_waiters.clear()
