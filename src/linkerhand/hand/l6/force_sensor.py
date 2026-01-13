"""Force sensor data acquisition for L6 robotic hand.

This module provides force sensor management for the L6 robotic hand:

- SingleForceSensorManager: Manages a single finger's force sensor (requires command_prefix).
- ForceSensorManager: Manages all 5 fingers' force sensors (thumb, index, middle, ring, pinky).

Each finger has a unique command prefix (0xB1-0xB5) for CAN bus communication.
Force sensor data is transmitted across 12 CAN frames, each containing 6 bytes,
for a total of 72 bytes per finger.
"""

import queue
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass, field

import can

from linkerhand.comm import CANMessageDispatcher
from linkerhand.exceptions import StateError, TimeoutError, ValidationError


@dataclass(frozen=True)
class ForceSensorData:
    """Immutable force sensor data container.

    Attributes:
        values: Tuple of 72 bytes representing force sensor readings.
        timestamp: Unix timestamp when the data was assembled.
    """

    values: tuple
    timestamp: float


@dataclass(frozen=True)
class FrameBatch:
    """Immutable batch of CAN message frames for assembling complete sensor data.

    Force sensor data is transmitted across 12 CAN frames, each containing 6 bytes.
    This class accumulates frames and assembles them into complete ForceSensorData.

    Attributes:
        frames: Mapping from frame index (0-11) to 6-byte data payload.
        started_at: Unix timestamp when the first frame of this batch was received.
    """

    frames: Mapping[int, bytes] = field(default_factory=dict)
    started_at: float = field(default_factory=time.time)

    def add_frame(self, frame_id: int, data: bytes) -> "FrameBatch":
        """Create a new FrameBatch with an additional frame.

        Args:
            frame_id: Frame index (0-11).
            data: 6-byte frame payload.

        Returns:
            New FrameBatch instance with the added frame.

        Note:
            This method does not modify the current instance (immutable pattern).
        """
        new_frames = {**self.frames, frame_id: data}
        return FrameBatch(frames=new_frames, started_at=self.started_at)

    def is_complete(self) -> bool:
        """Check if all 12 frames have been received.

        Returns:
            True if all frames (0-11) are present, False otherwise.
        """
        return len(self.frames) == 12

    def assemble(self) -> ForceSensorData:
        """Assemble the complete 72-byte force sensor data.

        Returns:
            ForceSensorData instance with all 72 bytes assembled.

        Raises:
            KeyError: If any frame index (0-11) is missing.
        """
        data = bytearray(72)
        for i in range(12):
            data[i * 6 : (i + 1) * 6] = self.frames[i]
        return ForceSensorData(values=tuple(data), timestamp=time.time())


class SingleForceSensorManager:
    """Manager for a single finger's force sensor data acquisition via CAN bus.

    This class handles multi-frame force sensor data acquisition with three access modes:
    1. Blocking mode: get_data_blocking() - wait for next complete data with timeout
    2. Streaming mode: stream() - continuous polling with Queue-based delivery
    3. Cache mode: get_latest_data() - non-blocking read of most recent data

    The manager uses an immutable data design for thread-safe operation without locks
    for data access. All CAN message processing happens in the dispatcher's thread.

    Attributes:
        _dispatcher: CAN message dispatcher for send/receive operations.
        _frame_batch: Current batch of frames being assembled (or None).
        _latest_data: Most recently assembled complete sensor data (or None).
        _blocking_waiters: List of (event, result_holder) for blocking callers.
        _waiters_lock: Lock protecting the blocking waiters list.
        _streaming_queue: Queue for streaming mode data delivery (or None if not streaming).
        _streaming_timer: Background thread for periodic requests (or None).
        _streaming_interval_ms: Interval in milliseconds for streaming requests.
    """

    # CAN protocol constants
    _FRAME_COUNT = 12
    _BYTES_PER_FRAME = 6

    def __init__(
        self,
        arbitration_id: int,
        dispatcher: CANMessageDispatcher,
        command_prefix: int,
    ) -> None:
        """Initialize the force sensor manager.

        Args:
            arbitration_id: Arbitration ID for the force sensor requests.
            dispatcher: CAN message dispatcher to use for communication.
            command_prefix: Command prefix for the sensor (e.g., 0xB1-0xB5 for fingers).
        """
        self._arbitration_id = arbitration_id
        self._command_prefix = command_prefix
        self._request_cmd = [command_prefix, 0xC6]

        self._dispatcher = dispatcher
        self._dispatcher.subscribe(self._on_message)

        # Frame assembly state
        self._frame_batch: FrameBatch | None = None

        # Latest complete data cache
        self._latest_data: ForceSensorData | None = None

        # Blocking mode support
        self._blocking_waiters: list[tuple[threading.Event, dict]] = []
        self._waiters_lock = threading.Lock()

        # Streaming mode support
        self._streaming_queue: queue.Queue[ForceSensorData] | None = None
        self._streaming_timer: threading.Thread | None = None
        self._streaming_interval_ms: float | None = None

    def get_data_blocking(self, timeout_ms: float = 1000) -> ForceSensorData:
        """Get force sensor data with blocking wait.

        This method registers a waiter and blocks until complete sensor data
        is received or the timeout expires. If streaming mode is active, this
        method may receive data from streaming requests.

        Args:
            timeout_ms: Maximum time to wait in milliseconds (default: 1000).

        Returns:
            Complete force sensor data.

        Raises:
            TimeoutError: If no complete data is received within timeout.
            ValidationError: If timeout_ms is not positive.

        Example:
            >>> manager = ForceSensorManager(arbitration_id, dispatcher)
            >>> try:
            ...     data = manager.get_data_blocking(timeout_ms=500)
            ...     print(f"Received {len(data.values)} bytes")
            ... except TimeoutError:
            ...     print("Request timed out")
        """
        if timeout_ms <= 0:
            raise ValidationError("timeout_ms must be positive")

        event = threading.Event()
        result_holder: dict[str, ForceSensorData | None] = {"data": None}

        # Register this waiter
        with self._waiters_lock:
            self._blocking_waiters.append((event, result_holder))

        self._send_request()

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
            raise TimeoutError(f"No data received within {timeout_ms}ms")

    def stream(
        self, interval_ms: float = 100, maxsize: int = 100
    ) -> queue.Queue[ForceSensorData]:
        """Start streaming mode with periodic data requests.

        Creates a Queue and starts a background thread that periodically requests
        sensor data. Complete data is automatically pushed to the Queue.

        Args:
            interval_ms: Request interval in milliseconds (default: 100).
            maxsize: Maximum Queue size (default: 100). When full, oldest data is dropped.

        Returns:
            Queue instance for receiving ForceSensorData.

        Raises:
            StateError: If streaming is already active.
            ValidationError: If interval_ms is not positive or maxsize is not positive.

        Example:
            >>> manager = ForceSensorManager(arbitration_id, dispatcher)
            >>> q = manager.stream(interval_ms=100)
            >>> try:
            ...     while True:
            ...         data = q.get(timeout=1.0)
            ...         process(data)
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
            target=self._streaming_loop, daemon=True, name="ForceSensor-Streaming"
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

    def get_latest_data(self) -> ForceSensorData | None:
        """Get the most recent cached sensor data (non-blocking).

        This method returns the last complete sensor data that was received,
        without sending any new requests. It returns None if no data has been
        received yet.

        Returns:
            Latest ForceSensorData or None if no data received yet.

        Example:
            >>> data = manager.get_latest_data()
            >>> if data:
            ...     age = time.time() - data.timestamp
            ...     if age < 0.1:  # Less than 100ms old
            ...         print("Data is fresh")
        """
        return self._latest_data

    def _send_request(self) -> None:
        """Send a force sensor data request via CAN bus.

        Sends a CAN message with the configured arbitration_id and command.
        """
        msg = can.Message(
            arbitration_id=self._arbitration_id,
            data=self._request_cmd,
            is_extended_id=False,
        )
        self._dispatcher.send(msg)

    def _streaming_loop(self) -> None:
        """Background thread loop for streaming mode.

        Periodically sends sensor data requests at the configured interval.
        The loop continues until _streaming_timer is set to None by stop_streaming().
        """
        if self._streaming_interval_ms is None:
            raise StateError("Streaming is not active. Call stream() first.")
        while self._streaming_timer is not None:
            self._send_request()
            time.sleep(self._streaming_interval_ms / 1000.0)

    def _on_message(self, msg: can.Message) -> None:
        """Handle incoming CAN messages (callback from dispatcher thread).

        Filters for force sensor response frames, assembles them into complete
        data, and dispatches complete data to all waiting consumers.

        Args:
            msg: CAN message from the bus.

        Note:
            This method executes in the dispatcher's receive thread and must
            return quickly to avoid blocking message reception.
        """
        # Filter: only process messages with correct arbitration ID
        if msg.arbitration_id != self._arbitration_id:
            return

        # Filter: only process sensor response frames
        if len(msg.data) < 8 or msg.data[0] != self._command_prefix:
            return

        # Extract frame information
        # Frame index is encoded in high 4 bits: 0x00, 0x10, 0x20, ..., 0xB0
        frame_idx = msg.data[1] >> 4  # Extract high nibble: 0-11
        frame_data = bytes(msg.data[2:8])  # 6 bytes of payload

        # Validate frame index
        if frame_idx >= self._FRAME_COUNT:
            return

        # Add frame to current batch
        if self._frame_batch is None:
            self._frame_batch = FrameBatch()

        self._frame_batch = self._frame_batch.add_frame(frame_idx, frame_data)

        # Check if we have all frames
        if self._frame_batch.is_complete():
            # Assemble complete data
            complete_data = self._frame_batch.assemble()

            # Reset batch for next set of frames
            self._frame_batch = None

            # Dispatch to all consumers
            self._on_complete_data(complete_data)

    def _on_complete_data(self, data: ForceSensorData) -> None:
        """Handle complete sensor data by dispatching to all consumers.

        This method:
        1. Updates the cached latest data
        2. Wakes up all blocking waiters
        3. Pushes data to the streaming queue (if active)

        Args:
            data: Complete force sensor data to distribute.

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


class ForceSensorManager:
    """Manager for all finger force sensors on the L6 robotic hand.

    This class manages force sensors for all 5 fingers (thumb, index, middle, ring, pinky)
    by coordinating multiple SingleForceSensorManager instances. It provides unified access
    to all finger sensor data.

    Each finger has a unique command prefix:
    - Thumb: 0xB1
    - Index: 0xB2
    - Middle: 0xB3
    - Ring: 0xB4
    - Pinky: 0xB5

    Attributes:
        _arbitration_id: CAN arbitration ID for sensor communication.
        _dispatcher: CAN message dispatcher shared by all finger sensors.
        _fingers: Dictionary mapping finger names to their SingleForceSensorManager instances.
    """

    # Finger command prefix mapping
    FINGER_COMMANDS = {
        "thumb": 0xB1,
        "index": 0xB2,
        "middle": 0xB3,
        "ring": 0xB4,
        "pinky": 0xB5,
    }

    def __init__(self, arbitration_id: int, dispatcher: CANMessageDispatcher) -> None:
        """Initialize the hand force sensor manager.

        Args:
            arbitration_id: CAN arbitration ID for sensor requests.
            dispatcher: CAN message dispatcher for communication.
        """
        self._arbitration_id = arbitration_id
        self._dispatcher = dispatcher

        # Create a SingleForceSensorManager for each finger
        self._fingers: dict[str, SingleForceSensorManager] = {
            finger_name: SingleForceSensorManager(
                arbitration_id=arbitration_id,
                dispatcher=dispatcher,
                command_prefix=cmd_prefix,
            )
            for finger_name, cmd_prefix in self.FINGER_COMMANDS.items()
        }

    def get_data_blocking(self, timeout_ms: float = 1000) -> dict[str, ForceSensorData]:
        """Get force sensor data for all fingers with blocking wait.

        This method requests data from all fingers and waits for all responses.
        Each finger is queried independently.

        Args:
            timeout_ms: Maximum time to wait per finger in milliseconds (default: 1000).

        Returns:
            Dictionary mapping finger names to their ForceSensorData.

        Raises:
            TimeoutError: If any finger fails to respond within timeout.
            ValidationError: If timeout_ms is not positive.

        Example:
            >>> manager = ForceSensorManager(arbitration_id, dispatcher)
            >>> all_data = manager.get_all_data_blocking(timeout_ms=500)
            >>> print(f"Thumb force: {all_data['thumb'].values[0]}")
        """
        if timeout_ms <= 0:
            raise ValidationError("timeout_ms must be positive")

        result = {}
        for finger_name, sensor in self._fingers.items():
            result[finger_name] = sensor.get_data_blocking(timeout_ms=timeout_ms)
        return result

    def stream(
        self, interval_ms: float = 100, maxsize: int = 100
    ) -> dict[str, queue.Queue[ForceSensorData]]:
        """Start streaming mode for all fingers.

        Creates a Queue for each finger and starts background threads that periodically
        request sensor data. Complete data is automatically pushed to the respective Queues.

        Args:
            interval_ms: Request interval in milliseconds (default: 100).
            maxsize: Maximum Queue size per finger (default: 100).

        Returns:
            Dictionary mapping finger names to their Queue instances.

        Raises:
            StateError: If any finger is already streaming.
            ValidationError: If interval_ms or maxsize is not positive.

        Example:
            >>> manager = ForceSensorManager(arbitration_id, dispatcher)
            >>> queues = manager.stream_all(interval_ms=100)
            >>> try:
            ...     while True:
            ...         thumb_data = queues['thumb'].get(timeout=1.0)
            ...         index_data = queues['index'].get(timeout=1.0)
            ...         process(thumb_data, index_data)
            ... finally:
            ...     manager.stop_streaming_all()
        """
        if interval_ms <= 0:
            raise ValidationError("interval_ms must be positive")
        if maxsize <= 0:
            raise ValidationError("maxsize must be positive")

        result = {}
        for finger_name, sensor in self._fingers.items():
            result[finger_name] = sensor.stream(
                interval_ms=interval_ms, maxsize=maxsize
            )
        return result

    def stop_streaming(self) -> None:
        """Stop streaming mode for all fingers.

        Stops all background request threads and clears all Queues. This method
        is idempotent and safe to call multiple times.

        Example:
            >>> manager.stop_streaming_all()
        """
        for sensor in self._fingers.values():
            sensor.stop_streaming()

    def get_latest_data(self) -> dict[str, ForceSensorData | None]:
        """Get the most recent cached sensor data for all fingers (non-blocking).

        This method returns the last complete sensor data that was received for
        each finger, without sending any new requests.

        Returns:
            Dictionary mapping finger names to their latest ForceSensorData or None.

        Example:
            >>> all_data = manager.get_all_latest_data()
            >>> for finger, data in all_data.items():
            ...     if data:
            ...         print(f"{finger}: {len(data.values)} bytes")
            ...     else:
            ...         print(f"{finger}: No data yet")
        """
        return {
            finger_name: sensor.get_latest_data()
            for finger_name, sensor in self._fingers.items()
        }
