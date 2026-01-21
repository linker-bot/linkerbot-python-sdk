"""Current sensing for L6 robotic hand.

This module provides the CurrentManager class for reading motor current
sensor data via CAN bus communication.
"""

import queue
import threading
import time
from dataclasses import dataclass

import can

from linkerhand.comm import CANMessageDispatcher
from linkerhand.exceptions import StateError, TimeoutError, ValidationError
from linkerhand.queue import IterableQueue


@dataclass(frozen=True)
class CurrentData:
    """Immutable current data container.

    Attributes:
        currents: Tuple of motor currents (6 values, range 0-255).
        timestamp: Unix timestamp when the data was received.
    """

    currents: tuple
    timestamp: float


class CurrentManager:
    """Manager for motor current sensing via CAN bus.

    This class handles current operations with three access modes:
    1. Blocking mode: get_currents_blocking() - request and wait for 6 currents
    2. Streaming mode: stream() - continuous polling with Queue-based delivery
    3. Cache reading: get_current_currents() - non-blocking read of cached currents

    The manager uses an immutable data design for thread-safe operation without locks
    for data access. All CAN message processing happens in the dispatcher's thread.

    CAN Protocol:
        - Sensing: Send [0x36] -> Receive [0x36, current1...current6]

    Attributes:
        _dispatcher: CAN message dispatcher for send/receive operations.
        _latest_data: Most recently received current data (or None).
        _blocking_waiters: List of (event, result_holder) for blocking callers.
        _waiters_lock: Lock protecting the blocking waiters list.
        _streaming_queue: Queue for streaming mode data delivery (or None if not streaming).
        _streaming_timer: Background thread for periodic requests (or None).
        _streaming_interval_ms: Interval in milliseconds for streaming requests.
    """

    # CAN protocol constants
    _SENSE_CMD = 0x36
    _SENSE_CMD_DATA = [0x36]
    _CURRENT_COUNT = 6

    def __init__(self, arbitration_id: int, dispatcher: CANMessageDispatcher) -> None:
        """Initialize the current manager.

        Args:
            arbitration_id: CAN arbitration ID for current sensing.
            dispatcher: CAN message dispatcher to use for communication.
        """
        self._arbitration_id = arbitration_id
        self._dispatcher = dispatcher
        self._dispatcher.subscribe(self._on_message)

        # Latest current data cache
        self._latest_data: CurrentData | None = None

        # Blocking mode support
        self._blocking_waiters: list[tuple[threading.Event, dict]] = []
        self._waiters_lock = threading.Lock()

        # Streaming mode support
        self._streaming_queue: IterableQueue[CurrentData] | None = None
        self._streaming_timer: threading.Thread | None = None
        self._streaming_interval_ms: float | None = None

    def get_currents_blocking(self, timeout_ms: float = 100) -> CurrentData:
        """Request and wait for current motor currents (blocking).

        This method sends a sensing request and blocks until 6 currents
        are received or the timeout expires. If streaming mode is active, this
        method may receive data from streaming requests.

        Args:
            timeout_ms: Maximum time to wait in milliseconds (default: 100).

        Returns:
            CurrentData instance containing currents and timestamp.

        Raises:
            TimeoutError: If no response is received within timeout.
            ValidationError: If timeout_ms is not positive.

        Example:
            >>> manager = CurrentManager(arbitration_id, dispatcher)
            >>> try:
            ...     data = manager.get_currents_blocking(timeout_ms=500)
            ...     print(f"Current currents: {data.currents}")
            ... except TimeoutError:
            ...     print("Request timed out")
        """
        if timeout_ms <= 0:
            raise ValidationError("timeout_ms must be positive")

        event = threading.Event()
        result_holder: dict[str, CurrentData | None] = {"data": None}

        # Register this waiter
        with self._waiters_lock:
            self._blocking_waiters.append((event, result_holder))

        # Send request only if not streaming (streaming already sends periodically)
        if self._streaming_queue is None:
            self._send_sense_request()

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
            raise TimeoutError(f"No current data received within {timeout_ms}ms")

    def get_current_currents(self) -> CurrentData | None:
        """Get the most recent cached current data (non-blocking).

        This method returns the last received current data without sending
        any new requests.

        Returns:
            CurrentData instance or None if no data received yet.

        Example:
            >>> data = manager.get_current_currents()
            >>> if data:
            ...     age = time.time() - data.timestamp
            ...     if age < 0.1:  # Less than 100ms old
            ...         print(f"Fresh currents: {data.currents}")
        """
        return self._latest_data

    def stream(
        self, interval_ms: float = 100, maxsize: int = 100
    ) -> IterableQueue[CurrentData]:
        """Start streaming mode with periodic current requests.

        Creates an IterableQueue and starts a background thread that periodically requests
        current data. Complete data is automatically pushed to the queue.

        The returned queue supports for-loop iteration and blocks when empty (like Go channels).

        Args:
            interval_ms: Request interval in milliseconds (default: 100).
            maxsize: Maximum queue size (default: 100). When full, oldest data is dropped.

        Returns:
            IterableQueue[CurrentData] instance for receiving CurrentData.

        Raises:
            StateError: If streaming is already active.
            ValidationError: If interval_ms is not positive or maxsize is not positive.

        Example:
            >>> manager = CurrentManager(arbitration_id, dispatcher)
            >>> q = manager.stream(interval_ms=100)
            >>> try:
            ...     for data in q:
            ...         print(f"Currents: {data.currents}")
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

        # Create queue and configure streaming
        self._streaming_queue = IterableQueue(maxsize=maxsize)
        self._streaming_interval_ms = interval_ms

        # Start background thread for periodic requests
        self._streaming_timer = threading.Thread(
            target=self._streaming_loop, daemon=True, name="CurrentManager-Streaming"
        )
        self._streaming_timer.start()

        return self._streaming_queue

    def stop_streaming(self) -> None:
        """Stop streaming mode and clean up resources.

        Stops the background request thread and closes the queue, which will
        end any for-loop iteration. This method is idempotent and safe to call
        multiple times.

        Example:
            >>> manager.stop_streaming()
        """
        if self._streaming_queue is None:
            return

        # Signal thread to stop by clearing the timer reference
        self._streaming_timer = None

        # Close the queue to signal end of iteration
        self._streaming_queue.close()

        self._streaming_queue = None
        self._streaming_interval_ms = None

    def _send_sense_request(self) -> None:
        """Send a current sensing request via CAN bus.

        Sends a CAN message with data=[0x36] to request current currents.
        """
        msg = can.Message(
            arbitration_id=self._arbitration_id,
            data=self._SENSE_CMD_DATA,
            is_extended_id=False,
        )
        self._dispatcher.send(msg)

    def _streaming_loop(self) -> None:
        """Background thread loop for streaming mode.

        Periodically sends current sensing requests at the configured interval.
        The loop continues until _streaming_timer is set to None by stop_streaming().
        """
        if self._streaming_interval_ms is None:
            raise StateError("Streaming is not active. Call stream() first.")
        while self._streaming_timer is not None:
            self._send_sense_request()
            time.sleep(self._streaming_interval_ms / 1000.0)

    def _on_message(self, msg: can.Message) -> None:
        """Handle incoming CAN messages (callback from dispatcher thread).

        Filters for current response messages and updates cache or wakes waiters.

        Args:
            msg: CAN message from the bus.

        Note:
            This method executes in the dispatcher's receive thread and must
            return quickly to avoid blocking message reception.
        """
        # Filter: only process messages with correct arbitration ID
        if msg.arbitration_id != self._arbitration_id:
            return

        # Filter: only process current response messages (start with 0x36)
        if len(msg.data) < 2 or msg.data[0] != self._SENSE_CMD:
            return

        # Parse current data (skip first byte which is the command)
        currents = tuple(msg.data[1:])

        # Validate current count (should be 6 currents)
        if len(currents) != self._CURRENT_COUNT:
            return

        # Create immutable current data
        current_data = CurrentData(currents=currents, timestamp=time.time())

        # Dispatch to all consumers
        self._on_complete_data(current_data)

    def _on_complete_data(self, data: CurrentData) -> None:
        """Handle complete current data by dispatching to all consumers.

        This method:
        1. Updates the cached latest data
        2. Wakes up all blocking waiters
        3. Pushes data to the streaming queue (if active)

        Args:
            data: Complete current data to distribute.

        Note:
            This method executes in the dispatcher's receive thread.
        """
        # 1. Update cache (atomic reference assignment)
        self._latest_data = data

        # 2. Wake up all blocking waiters
        with self._waiters_lock:
            for event, result_holder in self._blocking_waiters:
                result_holder["data"] = data
                event.set()
            self._blocking_waiters.clear()

        # 3. Push to streaming queue if active
        if self._streaming_queue is None:
            return
        try:
            # Non-blocking put
            self._streaming_queue.put_nowait(data)
        except queue.Full:
            # Queue full - remove oldest and try again
            try:
                self._streaming_queue.get_nowait()
                self._streaming_queue.put_nowait(data)
            except queue.Empty:
                pass  # Race condition: queue was emptied by consumer
