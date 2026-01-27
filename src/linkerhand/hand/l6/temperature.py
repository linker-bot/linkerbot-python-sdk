"""Temperature sensing for L6 robotic hand.

This module provides the TemperatureManager class for reading motor temperature
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

from .types import L6Temperature


@dataclass(frozen=True)
class TemperatureData:
    """Immutable temperature data container.

    Attributes:
        temperatures: L6Temperature instance containing motor temperatures in degrees Celsius (°C).
        timestamp: Unix timestamp when the data was received.
    """

    temperatures: L6Temperature
    timestamp: float


class TemperatureManager:
    """Manager for motor temperature sensing via CAN bus.

    This class handles temperature operations with three access modes:
    1. Blocking mode: get_temperatures_blocking() - request and wait for 6 temperatures
    2. Streaming mode: stream() - continuous polling with Queue-based delivery
    3. Cache reading: get_current_temperatures() - non-blocking read of cached temperatures

    The manager uses an immutable data design for thread-safe operation without locks
    for data access. All CAN message processing happens in the dispatcher's thread.

    CAN Protocol:
        - Sensing: Send [0x33] -> Receive [0x33, temp1...temp6]

    Attributes:
        _dispatcher: CAN message dispatcher for send/receive operations.
        _latest_data: Most recently received temperature data (or None).
        _blocking_waiters: List of (event, result_holder) for blocking callers.
        _waiters_lock: Lock protecting the blocking waiters list.
        _streaming_queue: Queue for streaming mode data delivery (or None if not streaming).
        _streaming_timer: Background thread for periodic requests (or None).
        _streaming_interval_ms: Interval in milliseconds for streaming requests.
    """

    # CAN protocol constants
    _SENSE_CMD = 0x33
    _SENSE_CMD_DATA = [0x33]
    _TEMPERATURE_COUNT = 6

    def __init__(self, arbitration_id: int, dispatcher: CANMessageDispatcher) -> None:
        """Initialize the temperature manager.

        Args:
            arbitration_id: CAN arbitration ID for temperature sensing.
            dispatcher: CAN message dispatcher to use for communication.
        """
        self._arbitration_id = arbitration_id
        self._dispatcher = dispatcher
        self._dispatcher.subscribe(self._on_message)

        # Latest temperature data cache
        self._latest_data: TemperatureData | None = None

        # Blocking mode support
        self._blocking_waiters: list[tuple[threading.Event, dict]] = []
        self._waiters_lock = threading.Lock()

        # Streaming mode support
        self._streaming_queue: IterableQueue[TemperatureData] | None = None
        self._streaming_timer: threading.Thread | None = None
        self._streaming_interval_ms: float | None = None

    def get_temperatures_blocking(self, timeout_ms: float = 100) -> TemperatureData:
        """Request and wait for current motor temperatures (blocking).

        This method sends a sensing request and blocks until 6 temperatures
        are received or the timeout expires. If streaming mode is active, this
        method may receive data from streaming requests.

        Args:
            timeout_ms: Maximum time to wait in milliseconds (default: 100).

        Returns:
            TemperatureData instance containing temperatures and timestamp.

        Raises:
            TimeoutError: If no response is received within timeout.
            ValidationError: If timeout_ms is not positive.

        Example:
            >>> manager = TemperatureManager(arbitration_id, dispatcher)
            >>> try:
            ...     data = manager.get_temperatures_blocking(timeout_ms=500)
            ...     print(f"Current temperatures: {data.temperatures}")
            ... except TimeoutError:
            ...     print("Request timed out")
        """
        if timeout_ms <= 0:
            raise ValidationError("timeout_ms must be positive")

        event = threading.Event()
        result_holder: dict[str, TemperatureData | None] = {"data": None}

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
            raise TimeoutError(f"No temperature data received within {timeout_ms}ms")

    def get_current_temperatures(self) -> TemperatureData | None:
        """Get the most recent cached temperature data (non-blocking).

        This method returns the last received temperature data without sending
        any new requests.

        Returns:
            TemperatureData instance or None if no data received yet.

        Example:
            >>> data = manager.get_current_temperatures()
            >>> if data:
            ...     age = time.time() - data.timestamp
            ...     if age < 0.1:  # Less than 100ms old
            ...         print(f"Fresh temperatures: {data.temperatures}")
        """
        return self._latest_data

    def stream(
        self, interval_ms: float = 100, maxsize: int = 100
    ) -> IterableQueue[TemperatureData]:
        """Start streaming mode with periodic temperature requests.

        Creates an IterableQueue and starts a background thread that periodically requests
        temperature data. Complete data is automatically pushed to the queue.

        The returned queue supports for-loop iteration and blocks when empty (like Go channels).

        Args:
            interval_ms: Request interval in milliseconds (default: 100).
            maxsize: Maximum queue size (default: 100). When full, oldest data is dropped.

        Returns:
            IterableQueue[TemperatureData] instance for receiving TemperatureData.

        Raises:
            StateError: If streaming is already active.
            ValidationError: If interval_ms is not positive or maxsize is not positive.

        Example:
            >>> manager = TemperatureManager(arbitration_id, dispatcher)
            >>> q = manager.stream(interval_ms=100)
            >>> try:
            ...     # Method 1: For-loop iteration (blocks when empty)
            ...     for data in q:
            ...         print(f"Temperatures: {data.temperatures}")
            ... finally:
            ...     manager.stop_streaming()
            >>>
            >>> # Method 2: Manual get() calls
            >>> q = manager.stream(interval_ms=100)
            >>> try:
            ...     while True:
            ...         data = q.get(timeout=1.0)
            ...         print(f"Temperatures: {data.temperatures}")
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
            target=self._streaming_loop,
            daemon=True,
            name="TemperatureManager-Streaming",
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
        """Send a temperature sensing request via CAN bus.

        Sends a CAN message with data=[0x33] to request current temperatures.
        """
        msg = can.Message(
            arbitration_id=self._arbitration_id,
            data=self._SENSE_CMD_DATA,
            is_extended_id=False,
        )
        self._dispatcher.send(msg)

    def _streaming_loop(self) -> None:
        """Background thread loop for streaming mode.

        Periodically sends temperature sensing requests at the configured interval.
        The loop continues until _streaming_timer is set to None by stop_streaming().
        """
        if self._streaming_interval_ms is None:
            raise StateError("Streaming is not active. Call stream() first.")
        while self._streaming_timer is not None:
            self._send_sense_request()
            time.sleep(self._streaming_interval_ms / 1000.0)

    def _on_message(self, msg: can.Message) -> None:
        """Handle incoming CAN messages (callback from dispatcher thread).

        Filters for temperature response messages and updates cache or wakes waiters.

        Args:
            msg: CAN message from the bus.

        Note:
            This method executes in the dispatcher's receive thread and must
            return quickly to avoid blocking message reception.
        """
        # Filter: only process messages with correct arbitration ID
        if msg.arbitration_id != self._arbitration_id:
            return

        # Filter: only process temperature response messages (start with 0x33)
        if len(msg.data) < 2 or msg.data[0] != self._SENSE_CMD:
            return

        # Parse temperature data (skip first byte which is the command)
        raw_temperatures = list(msg.data[1:])

        # Validate temperature count (should be 6 temperatures)
        if len(raw_temperatures) != self._TEMPERATURE_COUNT:
            return

        # Convert from raw CAN format (0-255) to L6Temperature (degrees Celsius)
        temperatures = L6Temperature.from_raw(raw_temperatures)

        # Create immutable temperature data
        temp_data = TemperatureData(temperatures=temperatures, timestamp=time.time())

        # Dispatch to all consumers
        self._on_complete_data(temp_data)

    def _on_complete_data(self, data: TemperatureData) -> None:
        """Handle complete temperature data by dispatching to all consumers.

        This method:
        1. Updates the cached latest data
        2. Wakes up all blocking waiters
        3. Pushes data to the streaming queue (if active)

        Args:
            data: Complete temperature data to distribute.

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
