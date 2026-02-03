"""Force sensor data acquisition for O6 robotic hand.

This module provides force sensor management for the O6 robotic hand:

- SingleForceSensorManager: Manages a single finger's force sensor.
- ForceSensorManager: Manages all 6 fingers' force sensors (thumb, index, middle, ring, pinky, palm).
"""

import queue
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass, field

import can
import numpy as np
import numpy.typing as npt

from linkerbot.comm import CANMessageDispatcher
from linkerbot.exceptions import StateError, TimeoutError, ValidationError
from linkerbot.queue import IterableQueue


@dataclass(frozen=True)
class ForceSensorData:
    """Immutable force sensor data container.

    Attributes:
        values: NumPy array of shape (10, 4) with dtype uint8 representing force sensor readings.
                Each row corresponds to a frame, and each frame contains 4 bytes.
        timestamp: Unix timestamp when the data was assembled.
    """

    values: npt.NDArray[np.uint8]
    timestamp: float


@dataclass(frozen=True)
class AllFingersData:
    """Immutable container for complete hand force sensor data from all 6 fingers.

    Attributes:
        thumb: Force sensor data from the thumb.
        index: Force sensor data from the index finger.
        middle: Force sensor data from the middle finger.
        ring: Force sensor data from the ring finger.
        pinky: Force sensor data from the pinky finger.
        palm: Force sensor data from the palm.
    """

    thumb: ForceSensorData
    index: ForceSensorData
    middle: ForceSensorData
    ring: ForceSensorData
    pinky: ForceSensorData


@dataclass(frozen=True)
class FrameBatch:
    """Internal helper for accumulating sensor data frames."""

    frames: Mapping[int, bytes] = field(default_factory=dict)
    started_at: float = field(default_factory=time.time)

    def add_frame(self, frame_id: int, data: bytes) -> "FrameBatch":
        new_frames = {**self.frames, frame_id: data}
        return FrameBatch(frames=new_frames, started_at=self.started_at)

    def is_complete(self) -> bool:
        return len(self.frames) == 10

    def assemble(self) -> ForceSensorData:
        data = bytearray(40)
        for i in range(10):
            data[i * 4 : (i + 1) * 4] = self.frames[i]
        return ForceSensorData(
            values=np.array(data, dtype=np.uint8).reshape(10, 4), timestamp=time.time()
        )


class SingleForceSensorManager:
    """Manager for a single finger's force sensor data acquisition.

    This class provides three access modes for force sensor operations:
    1. Blocking mode: get_data_blocking() - wait for next complete data with timeout
    2. Streaming mode: stream() - continuous polling with Queue-based delivery
    3. Cache mode: get_latest_data() - non-blocking read of most recent data
    """

    _FRAME_COUNT = 10
    _BYTES_PER_FRAME = 4

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
            command_prefix: Command prefix for the sensor.
        """
        self._arbitration_id = arbitration_id
        self._command_prefix = command_prefix
        self._request_cmd = [command_prefix, 0xA4]  # 0xA4 = 10x4 matrix

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
        self._streaming_queue: IterableQueue[ForceSensorData] | None = None
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
    ) -> IterableQueue[ForceSensorData]:
        """Start streaming mode with periodic data requests.

        Creates an IterableQueue and starts a background thread that periodically requests
        sensor data. Complete data is automatically pushed to the Queue.

        The returned queue supports for-loop iteration and blocks when empty (like Go channels).

        Args:
            interval_ms: Request interval in milliseconds (default: 100).
            maxsize: Maximum Queue size (default: 100). When full, oldest data is dropped.

        Returns:
            IterableQueue[ForceSensorData] instance for receiving ForceSensorData.

        Raises:
            StateError: If streaming is already active.
            ValidationError: If interval_ms is not positive or maxsize is not positive.

        Example:
            >>> manager = SingleForceSensorManager(arbitration_id, dispatcher, 0xB1)
            >>> q = manager.stream(interval_ms=100)
            >>> try:
            ...     # Method 1: For-loop iteration (blocks when empty)
            ...     for data in q:
            ...         process(data)
            ... finally:
            ...     manager.stop_streaming()
            >>>
            >>> # Method 2: Manual get() calls
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
        self._streaming_queue = IterableQueue(maxsize=maxsize)
        self._streaming_interval_ms = interval_ms

        # Start background thread for periodic requests
        self._streaming_timer = threading.Thread(
            target=self._streaming_loop, daemon=True, name="ForceSensor-Streaming"
        )
        self._streaming_timer.start()

        return self._streaming_queue

    def stop_streaming(self) -> None:
        """Stop streaming mode and clean up resources.

        Stops the background request thread and closes the Queue, which will
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
        msg = can.Message(
            arbitration_id=self._arbitration_id,
            data=self._request_cmd,
            is_extended_id=False,
        )
        self._dispatcher.send(msg)

    def _streaming_loop(self) -> None:
        if self._streaming_interval_ms is None:
            raise StateError("Streaming is not active. Call stream() first.")
        while self._streaming_timer is not None:
            self._send_request()
            time.sleep(self._streaming_interval_ms / 1000.0)

    def _on_message(self, msg: can.Message) -> None:
        # Filter: only process messages with correct arbitration ID
        if msg.arbitration_id != self._arbitration_id:
            return

        # Filter: only process sensor response frames
        if len(msg.data) < 6 or msg.data[0] != self._command_prefix:
            return

        # Extract frame information
        # BYTE1: position index (high nibble = row, low nibble = column)
        frame_idx = msg.data[1] >> 4  # Extract high nibble: 0-9
        frame_data = bytes(msg.data[2:6])  # 4 bytes of payload

        # Validate frame index
        if frame_idx >= self._FRAME_COUNT:
            return

        # Add frame to current batch
        if self._frame_batch is None:
            self._frame_batch = FrameBatch()

        self._frame_batch = self._frame_batch.add_frame(frame_idx, frame_data)

        # Check if we have all frames
        if self._frame_batch.is_complete():
            complete_data = self._frame_batch.assemble()
            self._frame_batch = None
            self._on_complete_data(complete_data)

    def _on_complete_data(self, data: ForceSensorData) -> None:
        # Update cache
        self._latest_data = data

        # Wake up all blocking waiters
        with self._waiters_lock:
            for event, result_holder in self._blocking_waiters:
                result_holder["data"] = data
                event.set()
            self._blocking_waiters.clear()

        # Push to streaming queue if active
        if self._streaming_queue is None:
            return
        try:
            self._streaming_queue.put_nowait(data)
        except queue.Full:
            # Queue full - remove oldest and try again
            try:
                self._streaming_queue.get_nowait()
                self._streaming_queue.put_nowait(data)
            except queue.Empty:
                pass  # Race condition: queue was emptied by consumer


class ForceSensorManager:
    """Manager for all finger force sensors on the O6 robotic hand.

    This class manages force sensors for all 6 fingers (thumb, index, middle, ring, pinky, palm)
    and provides unified access to sensor data from all fingers.
    """

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

        # Unified streaming mode support
        self._streaming_queue: IterableQueue[AllFingersData] | None = None
        self._aggregation_thread: threading.Thread | None = None
        self._finger_queues: dict[str, IterableQueue[ForceSensorData]] | None = None

    def get_data_blocking(self, timeout_ms: float = 1000) -> AllFingersData:
        """Get force sensor data for all fingers with blocking wait.

        This method requests data from all fingers and waits for all responses.
        Each finger is queried independently.

        Args:
            timeout_ms: Maximum time to wait per finger in milliseconds (default: 1000).

        Returns:
            AllFingersData containing force sensor data from all 6 fingers.

        Raises:
            TimeoutError: If any finger fails to respond within timeout.
            ValidationError: If timeout_ms is not positive.

        Example:
            >>> manager = ForceSensorManager(arbitration_id, dispatcher)
            >>> all_data = manager.get_data_blocking(timeout_ms=500)
            >>> print(f"Thumb force: {all_data.thumb.values[0]}")
        """
        if timeout_ms <= 0:
            raise ValidationError("timeout_ms must be positive")

        return AllFingersData(
            thumb=self._fingers["thumb"].get_data_blocking(timeout_ms=timeout_ms),
            index=self._fingers["index"].get_data_blocking(timeout_ms=timeout_ms),
            middle=self._fingers["middle"].get_data_blocking(timeout_ms=timeout_ms),
            ring=self._fingers["ring"].get_data_blocking(timeout_ms=timeout_ms),
            pinky=self._fingers["pinky"].get_data_blocking(timeout_ms=timeout_ms),
        )

    def stream(
        self, interval_ms: float = 100, maxsize: int = 100
    ) -> IterableQueue[AllFingersData]:
        """Start streaming mode for all fingers with unified data delivery.

        Creates a single IterableQueue and starts streaming for each finger independently.
        A background aggregation thread monitors all finger queues and combines their data
        into complete snapshots (AllFingersData) pushed to the unified queue.

        The returned queue supports for-loop iteration and blocks when empty (like Go channels).

        Args:
            interval_ms: Request interval in milliseconds (default: 100).
            maxsize: Maximum Queue size (default: 100). When full, oldest data is dropped.

        Returns:
            IterableQueue[AllFingersData] instance for receiving AllFingersData.
            Each item in the queue is a complete snapshot of all 6 fingers.

        Raises:
            StateError: If streaming is already active.
            ValidationError: If interval_ms or maxsize is not positive.

        Example:
            >>> manager = ForceSensorManager(arbitration_id, dispatcher)
            >>> q = manager.stream(interval_ms=100)
            >>> try:
            ...     # For-loop iteration (blocks when empty)
            ...     for all_data in q:
            ...         print(f"Thumb: {all_data.thumb.values[0]}")
            ...         print(f"Index: {all_data.index.values[0]}")
            ...         # Process data from all 6 fingers together
            ... finally:
            ...     manager.stop_streaming()
            >>>
            >>> # Method 2: Manual get() calls
            >>> q = manager.stream(interval_ms=100)
            >>> try:
            ...     while True:
            ...         all_data = q.get(timeout=1.0)
            ...         print(f"Thumb timestamp: {all_data.thumb.timestamp}")
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

        # Create unified output queue
        self._streaming_queue = IterableQueue(maxsize=maxsize)

        # Start streaming for each finger independently
        self._finger_queues = {}
        for finger_name, sensor in self._fingers.items():
            self._finger_queues[finger_name] = sensor.stream(
                interval_ms=interval_ms, maxsize=maxsize
            )

        # Start aggregation thread to combine data from all fingers
        self._aggregation_thread = threading.Thread(
            target=self._aggregation_loop,
            daemon=True,
            name="ForceSensorManager-Aggregation",
        )
        self._aggregation_thread.start()

        return self._streaming_queue

    def stop_streaming(self) -> None:
        """Stop streaming mode.

        Stops all finger streaming, the aggregation thread, and closes the queue,
        which will end any for-loop iteration. This method is idempotent and safe
        to call multiple times.

        Example:
            >>> manager.stop_streaming()
        """
        if self._streaming_queue is None:
            return

        # Stop streaming for all fingers
        for sensor in self._fingers.values():
            sensor.stop_streaming()

        # Signal aggregation thread to stop
        self._aggregation_thread = None

        # Close the unified queue to signal end of iteration
        self._streaming_queue.close()

        self._streaming_queue = None
        self._finger_queues = None

    def _aggregation_loop(self) -> None:
        if self._finger_queues is None:
            raise StateError("Streaming is not active. Call stream() first.")

        intermediate_queue: queue.Queue = queue.Queue()

        def read_finger_queue(
            finger_name: str, finger_queue: IterableQueue[ForceSensorData]
        ) -> None:
            try:
                for data in finger_queue:
                    intermediate_queue.put((finger_name, data))
            except StopIteration:
                return

        # Start a thread for each finger to concurrently wait for data
        reader_threads = []
        for finger_name, finger_queue in self._finger_queues.items():
            thread = threading.Thread(
                target=read_finger_queue,
                args=(finger_name, finger_queue),
                daemon=True,
                name=f"FingerReader-{finger_name}",
            )
            thread.start()
            reader_threads.append(thread)

        # Aggregation: collect data from intermediate queue and assemble complete snapshots
        latest_data: dict[str, ForceSensorData] = {}

        try:
            while self._aggregation_thread is not None:
                # Blocking wait for next finger data
                finger_name, data = intermediate_queue.get(timeout=1.0)
                latest_data[finger_name] = data

                # If we have data from all 6 fingers, create AllFingersData snapshot
                if len(latest_data) == 6:
                    complete_snapshot = AllFingersData(
                        thumb=latest_data["thumb"],
                        index=latest_data["index"],
                        middle=latest_data["middle"],
                        ring=latest_data["ring"],
                        pinky=latest_data["pinky"],
                    )

                    # Push to unified queue
                    if self._streaming_queue is not None:
                        try:
                            self._streaming_queue.put_nowait(complete_snapshot)
                        except queue.Full:
                            # Queue full - remove oldest and try again
                            try:
                                self._streaming_queue.get_nowait()
                                self._streaming_queue.put_nowait(complete_snapshot)
                            except queue.Empty:
                                pass  # Race condition: queue was emptied by consumer

                    # Clear latest_data to start collecting next snapshot
                    latest_data.clear()

        except queue.Empty:
            # Timeout waiting for data, check if we should continue
            pass
        except Exception:
            # Any unexpected error, exit gracefully
            return

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
