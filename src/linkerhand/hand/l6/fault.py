"""Fault management for L6 robotic hand.

This module provides the FaultManager class for clearing joint fault codes
and reading fault status.
"""

import queue
import threading
import time
from dataclasses import dataclass

import can

from linkerhand.comm import CANMessageDispatcher
from linkerhand.exceptions import StateError, TimeoutError, ValidationError
from linkerhand.queue import IterableQueue

from .types import L6Fault


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
