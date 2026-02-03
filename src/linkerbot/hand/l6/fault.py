"""Fault management for L6 robotic hand.

This module provides the FaultManager class for clearing joint fault codes
and reading fault status.
"""

import queue
import threading
import time
from dataclasses import dataclass
from enum import Flag

import can

from linkerbot.comm import CANMessageDispatcher
from linkerbot.exceptions import StateError, TimeoutError, ValidationError
from linkerbot.queue import IterableQueue


class FaultCode(Flag):
    """Motor fault code flags.

    Each bit represents a specific fault condition:
    - BIT0 (1): Phase B overcurrent
    - BIT1 (2): Phase C overcurrent
    - BIT2 (4): Phase A overcurrent
    - BIT3 (8): Overload level 1
    - BIT4 (16): Overload level 2
    - BIT5 (32): Motor overtemperature
    - BIT6 (64): MCU overtemperature
    - BIT7 (128): Reserved
    """

    NONE = 0
    PHASE_B_OVERCURRENT = 1 << 0  # BIT0: Phase B overcurrent
    PHASE_C_OVERCURRENT = 1 << 1  # BIT1: Phase C overcurrent
    PHASE_A_OVERCURRENT = 1 << 2  # BIT2: Phase A overcurrent
    OVERLOAD_1 = 1 << 3  # BIT3: Overload level 1
    OVERLOAD_2 = 1 << 4  # BIT4: Overload level 2
    MOTOR_OVERTEMP = 1 << 5  # BIT5: Motor overtemperature
    MCU_OVERTEMP = 1 << 6  # BIT6: MCU overtemperature

    def has_fault(self) -> bool:
        """Check if this fault code has any fault.

        Returns:
            True if any fault bit is set, False otherwise.

        Example:
            >>> code = FaultCode.PHASE_A_OVERCURRENT | FaultCode.OVERLOAD_1
            >>> code.has_fault()
            True
            >>> FaultCode.NONE.has_fault()
            False
        """
        return self != FaultCode.NONE

    def get_fault_names(self) -> list[str]:
        """Get human-readable fault names for this fault code.

        Returns:
            List of fault names. Returns ["No faults"] if no faults are present.

        Example:
            >>> code = FaultCode.PHASE_A_OVERCURRENT | FaultCode.OVERLOAD_1
            >>> code.get_fault_names()
            ['Phase A overcurrent', 'Overload level 1']
            >>> FaultCode.NONE.get_fault_names()
            ['No faults']
        """
        if not self.has_fault():
            return ["No faults"]

        names: list[str] = []
        if self & FaultCode.PHASE_B_OVERCURRENT:
            names.append("Phase B overcurrent")
        if self & FaultCode.PHASE_C_OVERCURRENT:
            names.append("Phase C overcurrent")
        if self & FaultCode.PHASE_A_OVERCURRENT:
            names.append("Phase A overcurrent")
        if self & FaultCode.OVERLOAD_1:
            names.append("Overload level 1")
        if self & FaultCode.OVERLOAD_2:
            names.append("Overload level 2")
        if self & FaultCode.MOTOR_OVERTEMP:
            names.append("Motor overtemperature")
        if self & FaultCode.MCU_OVERTEMP:
            names.append("MCU overtemperature")
        return names


@dataclass
class L6Fault:
    """Joint fault codes for L6 hand.

    Each attribute is a FaultCode enum value representing the fault status
    for that joint. You can directly call methods on each joint's fault code.

    Attributes:
        thumb_flex: Thumb flexion motor fault code
        thumb_abd: Thumb abduction motor fault code
        index: Index finger motor fault code
        middle: Middle finger motor fault code
        ring: Ring finger motor fault code
        pinky: Pinky finger motor fault code

    Example:
        >>> faults = L6Fault(...)
        >>> # Check if thumb flex has any fault
        >>> if faults.thumb_flex.has_fault():
        ...     print(f"Thumb flex faults: {faults.thumb_flex.get_fault_names()}")
        >>> # Check all joints
        >>> if faults.has_any_fault():
        ...     print("Some joints have faults")
        >>> # Access via index
        >>> print(faults[0].get_fault_names())  # thumb_flex
    """

    thumb_flex: FaultCode
    thumb_abd: FaultCode
    index: FaultCode
    middle: FaultCode
    ring: FaultCode
    pinky: FaultCode

    def to_list(self) -> list[FaultCode]:
        """Convert to list of FaultCode in joint order.

        Returns:
            List of 6 joint fault codes [thumb_flex, thumb_abd, index, middle, ring, pinky]
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
        return [int(code.value) & 0x7F for code in self.to_list()]

    @classmethod
    def from_list(cls, values: list[FaultCode]) -> "L6Fault":
        """Construct from list of FaultCode enum values.

        Args:
            values: List of 6 FaultCode values

        Returns:
            L6Fault instance

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

    @classmethod
    def from_raw(cls, values: list[int]) -> "L6Fault":
        # Internal: Construct from hardware communication format
        if len(values) != 6:
            raise ValueError(f"Expected 6 values, got {len(values)}")
        fault_codes = [FaultCode(v & 0x7F) for v in values]
        return cls.from_list(fault_codes)

    def has_any_fault(self) -> bool:
        """Check if any joint has a fault.

        Returns:
            True if any joint has a fault, False otherwise.

        Example:
            >>> faults = L6Fault(...)
            >>> if faults.has_any_fault():
            ...     print("At least one joint has a fault")
        """
        return any(code.has_fault() for code in self.to_list())

    def __getitem__(self, index: int) -> FaultCode:
        """Support indexing: faults[0] returns thumb_flex.

        Args:
            index: Joint index (0-5)

        Returns:
            Joint fault code value

        Raises:
            IndexError: If index is out of range
        """
        return self.to_list()[index]

    def __len__(self) -> int:
        """Return number of joints (always 6 for L6)."""
        return 6


@dataclass(frozen=True)
class FaultData:
    """Fault data container.

    Attributes:
        faults: L6Fault instance containing fault codes for all joints.
        timestamp: Timestamp when the data was received.
    """

    faults: L6Fault
    timestamp: float


class FaultManager:
    """Manager for joint fault management.

    This class provides fault management operations:
    1. Fault clearing: clear_faults() - clear all joint faults
    2. Blocking mode: get_faults_blocking() - request and wait for fault status
    3. Streaming mode: stream() - continuous polling with Queue-based delivery
    4. Cache reading: get_current_faults() - non-blocking read of cached faults
    """

    _CLEAR_FAULT_CMD = 0x83
    _READ_FAULT_CMD = 0x35
    _JOINT_COUNT = 6

    def __init__(self, arbitration_id: int, dispatcher: CANMessageDispatcher) -> None:
        """Initialize the fault manager.

        Args:
            arbitration_id: Device identifier for fault operations.
            dispatcher: Message dispatcher for communication.
        """
        self._arbitration_id = arbitration_id
        self._dispatcher = dispatcher
        self._dispatcher.subscribe(self._on_message)

        self._latest_data: FaultData | None = None
        self._blocking_waiters: list[tuple[threading.Event, dict]] = []
        self._waiters_lock = threading.Lock()
        self._streaming_queue: IterableQueue[FaultData] | None = None
        self._streaming_timer: threading.Thread | None = None
        self._streaming_interval_ms: float | None = None

    def clear_faults(self) -> None:
        """Clear fault codes for all joints.

        Example:
            >>> manager = FaultManager(arbitration_id, dispatcher)
            >>> manager.clear_faults()
        """
        data = [self._CLEAR_FAULT_CMD, 1, 1, 1, 1, 1, 1]
        msg = can.Message(
            arbitration_id=self._arbitration_id,
            data=data,
            is_extended_id=False,
        )
        self._dispatcher.send(msg)

    def get_faults_blocking(self, timeout_ms: float = 100) -> FaultData:
        """Get current fault status with blocking wait.

        Args:
            timeout_ms: Maximum time to wait in milliseconds (default: 100).

        Returns:
            FaultData instance containing fault status and timestamp.

        Raises:
            TimeoutError: If no response is received within timeout.
            ValidationError: If timeout_ms is not positive.

        Example:
            >>> manager = FaultManager(arbitration_id, dispatcher)
            >>> try:
            ...     data = manager.get_faults_blocking(timeout_ms=500)
            ...     if data.faults.has_any_fault():
            ...         # Access specific joint faults directly
            ...         print(f"Thumb flex: {data.faults.thumb_flex.get_fault_names()}")
            ...         print(f"Index: {data.faults.index.get_fault_names()}")
            ...         # Check if specific joint has fault
            ...         if data.faults.thumb_flex.has_fault():
            ...             print("Thumb flex has a fault!")
            ... except TimeoutError:
            ...     print("Request timed out")
        """
        if timeout_ms <= 0:
            raise ValidationError("timeout_ms must be positive")

        event = threading.Event()
        result_holder: dict[str, FaultData | None] = {"data": None}

        with self._waiters_lock:
            self._blocking_waiters.append((event, result_holder))

        if self._streaming_queue is None:
            self._send_fault_request()

        if event.wait(timeout_ms / 1000.0):
            if result_holder["data"] is None:
                raise TimeoutError(f"No data received within {timeout_ms}ms")
            return result_holder["data"]
        else:
            with self._waiters_lock:
                if (event, result_holder) in self._blocking_waiters:
                    self._blocking_waiters.remove((event, result_holder))
            raise TimeoutError(f"No fault data received within {timeout_ms}ms")

    def get_current_faults(self) -> FaultData | None:
        """Get the most recent fault data (non-blocking).

        Returns:
            FaultData instance or None if no data received yet.

        Example:
            >>> data = manager.get_current_faults()
            >>> if data:
            ...     age = time.time() - data.timestamp
            ...     if age < 0.1:  # Less than 100ms old
            ...         print(f"Fresh fault data: {data.faults.has_any_fault()}")
        """
        return self._latest_data

    def stream(
        self, interval_ms: float = 100, maxsize: int = 100
    ) -> IterableQueue[FaultData]:
        """Start streaming mode with periodic fault status polling.

        Returns a queue that receives fault data at regular intervals.
        The queue supports for-loop iteration and blocks when empty.

        Args:
            interval_ms: Polling interval in milliseconds (default: 100).
            maxsize: Maximum queue size (default: 100). When full, oldest data is dropped.

        Returns:
            IterableQueue[FaultData] instance for receiving FaultData.

        Raises:
            StateError: If streaming is already active.
            ValidationError: If interval_ms is not positive or maxsize is not positive.

        Example:
            >>> manager = FaultManager(arbitration_id, dispatcher)
            >>> q = manager.stream(interval_ms=100)
            >>> try:
            ...     # For-loop iteration (blocks when empty)
            ...     for data in q:
            ...         if data.faults.has_any_fault():
            ...             # Access each joint's faults
            ...             for joint_name in ['thumb_flex', 'thumb_abd', 'index', 'middle', 'ring', 'pinky']:
            ...                 fault_code = getattr(data.faults, joint_name)
            ...                 if fault_code.has_fault():
            ...                     print(f"{joint_name}: {fault_code.get_fault_names()}")
            ... finally:
            ...     manager.stop_streaming()
        """
        if interval_ms <= 0:
            raise ValidationError("interval_ms must be positive")
        if maxsize <= 0:
            raise ValidationError("maxsize must be positive")

        if self._streaming_queue is not None:
            raise StateError(
                "Streaming is already active. Call stop_streaming() first."
            )

        self._streaming_queue = IterableQueue(maxsize=maxsize)
        self._streaming_interval_ms = interval_ms

        self._streaming_timer = threading.Thread(
            target=self._streaming_loop, daemon=True, name="FaultManager-Streaming"
        )
        self._streaming_timer.start()

        return self._streaming_queue

    def stop_streaming(self) -> None:
        """Stop streaming mode and clean up resources.

        Ends any active for-loop iteration. Safe to call multiple times.

        Example:
            >>> manager.stop_streaming()
        """
        if self._streaming_queue is None:
            return

        self._streaming_timer = None
        self._streaming_queue.close()
        self._streaming_queue = None
        self._streaming_interval_ms = None

    def _send_fault_request(self) -> None:
        msg = can.Message(
            arbitration_id=self._arbitration_id,
            data=[self._READ_FAULT_CMD],
            is_extended_id=False,
        )
        self._dispatcher.send(msg)

    def _streaming_loop(self) -> None:
        if self._streaming_interval_ms is None:
            raise StateError("Streaming is not active. Call stream() first.")
        while self._streaming_timer is not None:
            self._send_fault_request()
            time.sleep(self._streaming_interval_ms / 1000.0)

    def _on_message(self, msg: can.Message) -> None:
        if msg.arbitration_id != self._arbitration_id:
            return

        if len(msg.data) < 7 or msg.data[0] != self._READ_FAULT_CMD:
            return

        raw_codes = list(msg.data[1:7])

        if len(raw_codes) != self._JOINT_COUNT:
            return

        faults = L6Fault.from_raw(raw_codes)
        fault_data = FaultData(faults=faults, timestamp=time.time())
        self._on_complete_data(fault_data)

    def _on_complete_data(self, data: FaultData) -> None:
        self._latest_data = data

        with self._waiters_lock:
            for event, result_holder in self._blocking_waiters:
                result_holder["data"] = data
                event.set()
            self._blocking_waiters.clear()

        if self._streaming_queue is None:
            return
        try:
            self._streaming_queue.put_nowait(data)
        except queue.Full:
            try:
                self._streaming_queue.get_nowait()
                self._streaming_queue.put_nowait(data)
            except queue.Empty:
                pass
