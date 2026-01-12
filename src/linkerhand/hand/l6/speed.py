"""Speed control and sensing for L6 robotic hand.

This module provides the SpeedManager class for controlling motor speeds
and reading speed sensor data via CAN bus communication.
"""

import queue
import threading
import time
from dataclasses import dataclass

import can

from linkerhand.comm import CANMessageDispatcher
from linkerhand.exceptions import StateError, TimeoutError, ValidationError


@dataclass(frozen=True)
class SpeedData:
    """Immutable speed data container.

    Attributes:
        speeds: Tuple of motor speeds (6 values, range 0-255).
        timestamp: Unix timestamp when the data was received.
    """

    speeds: tuple
    timestamp: float


class SpeedManager:
    """Manager for motor speed control and sensing via CAN bus.

    This class handles speed operations with four access modes:
    1. Speed control: set_speeds() - send 6 target speeds and cache response
    2. Blocking mode: get_speeds_blocking() - request and wait for 6 current speeds
    3. Streaming mode: stream() - continuous polling with Queue-based delivery
    4. Cache reading: get_current_speeds() - non-blocking read of cached speeds

    The manager uses an immutable data design for thread-safe operation without locks
    for data access. All CAN message processing happens in the dispatcher's thread.

    CAN Protocol:
        - Control: Send [0x05, speed1...speed6] -> Receive [0x05, current1...current6]
        - Sensing: Send [0x05] -> Receive [0x05, speed1...speed6]

    Attributes:
        _dispatcher: CAN message dispatcher for send/receive operations.
        _latest_data: Most recently received speed data (or None).
        _blocking_waiters: List of (event, result_holder) for blocking callers.
        _waiters_lock: Lock protecting the blocking waiters list.
        _streaming_queue: Queue for streaming mode data delivery (or None if not streaming).
        _streaming_timer: Background thread for periodic requests (or None).
        _streaming_interval_ms: Interval in milliseconds for streaming requests.
    """

    # CAN protocol constants
    _CONTROL_CMD = 0x05
    _SENSE_CMD = [0x05]
    _SPEED_COUNT = 6

    def __init__(self, arbitration_id: int, dispatcher: CANMessageDispatcher) -> None:
        """Initialize the speed manager.

        Args:
            arbitration_id: CAN arbitration ID for speed control/sensing.
            dispatcher: CAN message dispatcher to use for communication.
        """
        self._arbitration_id = arbitration_id
        self._dispatcher = dispatcher
        self._dispatcher.subscribe(self._on_message)

        # Latest speed data cache
        self._latest_data: SpeedData | None = None

        # Blocking mode support
        self._blocking_waiters: list[tuple[threading.Event, dict]] = []
        self._waiters_lock = threading.Lock()

        # Streaming mode support
        self._streaming_queue: queue.Queue[SpeedData] | None = None
        self._streaming_timer: threading.Thread | None = None
        self._streaming_interval_ms: float | None = None

    def set_speeds(self, speeds: tuple[int, ...] | list[int]) -> None:
        """Send target speeds to the robotic hand motors.

        This method sends 6 target speeds to the hand. The hand will respond
        with the current speeds, which are automatically cached and can be
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
            ...     print(f"Current speeds: {current[0]}")
        """
        # Validate input
        if len(speeds) != self._SPEED_COUNT:
            raise ValidationError(
                f"Expected {self._SPEED_COUNT} speeds, got {len(speeds)}"
            )

        # Validate speed values (0-255 range for byte encoding)
        for i, speed in enumerate(speeds):
            if not isinstance(speed, (int, float)):
                raise ValidationError(f"Speed {i} must be numeric, got {type(speed)}")
            if not 0 <= speed <= 255:
                raise ValidationError(f"Speed {i} value {speed} out of range [0, 255]")

        # Build and send CAN message
        data = [self._CONTROL_CMD] + [int(s) for s in speeds]
        msg = can.Message(
            arbitration_id=self._arbitration_id,
            data=data,
            is_extended_id=False,
        )
        self._dispatcher.send(msg)

    def get_speeds_blocking(self, timeout_ms: float = 100) -> tuple:
        """Request and wait for current motor speeds (blocking).

        This method sends a sensing request and blocks until 6 current speeds
        are received or the timeout expires. If streaming mode is active, this
        method may receive data from streaming requests.

        Args:
            timeout_ms: Maximum time to wait in milliseconds (default: 100).

        Returns:
            Tuple of 6 current motor speeds.

        Raises:
            TimeoutError: If no response is received within timeout.
            ValidationError: If timeout_ms is not positive.

        Example:
            >>> manager = SpeedManager(arbitration_id, dispatcher)
            >>> try:
            ...     speeds = manager.get_speeds_blocking(timeout_ms=500)
            ...     print(f"Current speeds: {speeds}")
            ... except TimeoutError:
            ...     print("Request timed out")
        """
        if timeout_ms <= 0:
            raise ValidationError("timeout_ms must be positive")

        event = threading.Event()
        result_holder: dict[str, tuple | None] = {"data": None}

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
            raise TimeoutError(f"No speed data received within {timeout_ms}ms")

    def get_current_speeds(self) -> tuple[tuple, float] | None:
        """Get the most recent cached speed data (non-blocking).

        This method returns the last received speed data (either from set_speeds()
        response or get_speeds_blocking() response) without sending any new requests.

        Returns:
            Tuple of (speeds, timestamp) or None if no data received yet.
            - speeds: Tuple of 6 speed values
            - timestamp: Unix timestamp when data was received

        Example:
            >>> data = manager.get_current_speeds()
            >>> if data:
            ...     speeds, timestamp = data
            ...     age = time.time() - timestamp
            ...     if age < 0.1:  # Less than 100ms old
            ...         print(f"Fresh speeds: {speeds}")
        """
        if self._latest_data is None:
            return None
        return (self._latest_data.speeds, self._latest_data.timestamp)

    def stream(
        self, interval_ms: float = 100, maxsize: int = 100
    ) -> queue.Queue[SpeedData]:
        """Start streaming mode with periodic speed requests.

        Creates a Queue and starts a background thread that periodically requests
        speed data. Complete data is automatically pushed to the Queue.

        Args:
            interval_ms: Request interval in milliseconds (default: 100).
            maxsize: Maximum Queue size (default: 100). When full, oldest data is dropped.

        Returns:
            Queue instance for receiving SpeedData.

        Raises:
            StateError: If streaming is already active.
            ValidationError: If interval_ms is not positive or maxsize is not positive.

        Example:
            >>> manager = SpeedManager(arbitration_id, dispatcher)
            >>> q = manager.stream(interval_ms=100)
            >>> try:
            ...     while True:
            ...         data = q.get(timeout=1.0)
            ...         print(f"Speeds: {data.speeds}")
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
        self._streaming_queue = queue.Queue(maxsize=maxsize)
        self._streaming_interval_ms = interval_ms

        # Start background thread for periodic requests
        self._streaming_timer = threading.Thread(
            target=self._streaming_loop, daemon=True, name="SpeedManager-Streaming"
        )
        self._streaming_timer.start()

        return self._streaming_queue

    def stop_streaming(self) -> None:
        """Stop streaming mode and clean up resources.

        Stops the background request thread and clears the Queue. This method
        is idempotent and safe to call multiple times.

        Example:
            >>> manager.stop_streaming()
        """
        if self._streaming_queue is None:
            return

        # Signal thread to stop by clearing the timer reference
        self._streaming_timer = None

        # Clear and discard the queue
        while not self._streaming_queue.empty():
            try:
                self._streaming_queue.get_nowait()
            except queue.Empty:
                break

        self._streaming_queue = None
        self._streaming_interval_ms = None

    def _send_sense_request(self) -> None:
        """Send a speed sensing request via CAN bus.

        Sends a CAN message with data=[0x05] to request current speeds.
        """
        msg = can.Message(
            arbitration_id=self._arbitration_id,
            data=self._SENSE_CMD,
            is_extended_id=False,
        )
        self._dispatcher.send(msg)

    def _streaming_loop(self) -> None:
        """Background thread loop for streaming mode.

        Periodically sends speed sensing requests at the configured interval.
        The loop continues until _streaming_timer is set to None by stop_streaming().
        """
        if self._streaming_interval_ms is None:
            raise StateError("Streaming is not active. Call stream() first.")
        while self._streaming_timer is not None:
            self._send_sense_request()
            time.sleep(self._streaming_interval_ms / 1000.0)

    def _on_message(self, msg: can.Message) -> None:
        """Handle incoming CAN messages (callback from dispatcher thread).

        Filters for speed response messages and updates cache or wakes waiters.

        Args:
            msg: CAN message from the bus.

        Note:
            This method executes in the dispatcher's receive thread and must
            return quickly to avoid blocking message reception.
        """
        # Filter: only process messages with correct arbitration ID
        if msg.arbitration_id != self._arbitration_id:
            return

        # Filter: only process speed response messages (start with 0x05)
        if len(msg.data) < 2 or msg.data[0] != self._CONTROL_CMD:
            return

        # Parse speed data (skip first byte which is the command)
        speeds = tuple(msg.data[1:])

        # Validate speed count (should be 6 speeds)
        if len(speeds) != self._SPEED_COUNT:
            return

        # Create immutable speed data
        speed_data = SpeedData(speeds=speeds, timestamp=time.time())

        # Dispatch to all consumers
        self._on_complete_data(speed_data)

    def _on_complete_data(self, data: SpeedData) -> None:
        """Handle complete speed data by dispatching to all consumers.

        This method:
        1. Updates the cached latest data
        2. Wakes up all blocking waiters
        3. Pushes data to the streaming queue (if active)

        Args:
            data: Complete speed data to distribute.

        Note:
            This method executes in the dispatcher's receive thread.
        """
        # 1. Update cache (atomic reference assignment)
        self._latest_data = data

        # 2. Wake up all blocking waiters
        with self._waiters_lock:
            for event, result_holder in self._blocking_waiters:
                result_holder["data"] = data.speeds
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
