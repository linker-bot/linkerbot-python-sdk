"""Torque control and sensing for L6 robotic hand.

This module provides the TorqueManager class for controlling joint torques
and reading torque sensor data via CAN bus communication.
"""

import queue
import threading
import time
from dataclasses import dataclass

import can

from linkerhand.comm import CANMessageDispatcher
from linkerhand.exceptions import StateError, TimeoutError, ValidationError
from linkerhand.queue import IterableQueue

from .types import L6Torque


@dataclass(frozen=True)
class TorqueData:
    """Immutable torque data container.

    Attributes:
        torques: L6Torque instance containing joint torques (0-100 range).
        timestamp: Unix timestamp when the data was received.
    """

    torques: L6Torque
    timestamp: float


class TorqueManager:
    """Manager for joint torque control and sensing via CAN bus.

    This class handles torque operations with four access modes:
    1. Torque control: set_torques() - send 6 target torques and cache response
    2. Blocking mode: get_torques_blocking() - request and wait for 6 current torques
    3. Streaming mode: stream() - continuous polling with Queue-based delivery
    4. Cache reading: get_current_torques() - non-blocking read of cached torques

    The manager uses an immutable data design for thread-safe operation without locks
    for data access. All CAN message processing happens in the dispatcher's thread.

    CAN Protocol:
        - Control: Send [0x02, torque1...torque6] -> Receive [0x02, current1...current6]
        - Sensing: Send [0x02] -> Receive [0x02, torque1...torque6]

    Attributes:
        _dispatcher: CAN message dispatcher for send/receive operations.
        _latest_data: Most recently received torque data (or None).
        _blocking_waiters: List of (event, result_holder) for blocking callers.
        _waiters_lock: Lock protecting the blocking waiters list.
        _streaming_queue: Queue for streaming mode data delivery (or None if not streaming).
        _streaming_timer: Background thread for periodic requests (or None).
        _streaming_interval_ms: Interval in milliseconds for streaming requests.
    """

    # CAN protocol constants
    _CONTROL_CMD = 0x02
    _SENSE_CMD = [0x02]
    _TORQUE_COUNT = 6

    def __init__(self, arbitration_id: int, dispatcher: CANMessageDispatcher) -> None:
        """Initialize the torque manager.

        Args:
            arbitration_id: CAN arbitration ID for torque control/sensing.
            dispatcher: CAN message dispatcher to use for communication.
        """
        self._arbitration_id = arbitration_id
        self._dispatcher = dispatcher
        self._dispatcher.subscribe(self._on_message)

        # Latest torque data cache
        self._latest_data: TorqueData | None = None

        # Blocking mode support
        self._blocking_waiters: list[tuple[threading.Event, dict]] = []
        self._waiters_lock = threading.Lock()

        # Streaming mode support
        self._streaming_queue: IterableQueue[TorqueData] | None = None
        self._streaming_timer: threading.Thread | None = None
        self._streaming_interval_ms: float | None = None

    def set_torques(self, torques: L6Torque | list[float]) -> None:
        """Send target torques to the robotic hand.

        This method sends 6 target torques to the hand. The hand will respond
        with the current torques, which are automatically cached and can be
        retrieved via get_current_torques().

        Args:
            torques: L6Torque instance or list of 6 target torques (range 0-100 each).

        Raises:
            ValidationError: If torques count is not 6 or values are out of range.

        Example:
            >>> manager = TorqueManager(arbitration_id, dispatcher)
            >>> # Using L6Torque instance
            >>> manager.set_torques(L6Torque(thumb_flex=50.0, thumb_abd=30.0,
            ...                              index=60.0, middle=60.0, ring=60.0, pinky=60.0))
            >>> # Using list
            >>> manager.set_torques([50.0, 30.0, 60.0, 60.0, 60.0, 60.0])
            >>> time.sleep(0.1)  # Wait for response
            >>> current = manager.get_current_torques()
            >>> if current:
            ...     print(f"Current torques: {current.torques.thumb_flex}")
        """
        # Convert to raw CAN format (0-255)
        if isinstance(torques, L6Torque):
            raw_torques = torques.to_raw()
        elif isinstance(torques, list):
            # Validate input
            if len(torques) != self._TORQUE_COUNT:
                raise ValidationError(
                    f"Expected {self._TORQUE_COUNT} torques, got {len(torques)}"
                )
            # Validate torque values (0-100 range)
            for i, torque in enumerate(torques):
                if not isinstance(torque, float):
                    raise ValidationError(
                        f"Torque {i} must be float, got {type(torque)}"
                    )
                if not 0 <= torque <= 100:
                    raise ValidationError(
                        f"Torque {i} value {torque} out of range [0, 100]"
                    )
            # Convert to raw CAN format
            raw_torques = L6Torque.from_list(torques).to_raw()

        # Build and send CAN message
        data = [self._CONTROL_CMD, *raw_torques]
        msg = can.Message(
            arbitration_id=self._arbitration_id,
            data=data,
            is_extended_id=False,
        )
        self._dispatcher.send(msg)

    def get_torques_blocking(self, timeout_ms: float = 100) -> TorqueData:
        """Request and wait for current joint torques (blocking).

        This method sends a sensing request and blocks until 6 current torques
        are received or the timeout expires. If streaming mode is active, this
        method may receive data from streaming requests.

        Args:
            timeout_ms: Maximum time to wait in milliseconds (default: 100).

        Returns:
            TorqueData instance containing torques and timestamp.

        Raises:
            TimeoutError: If no response is received within timeout.
            ValidationError: If timeout_ms is not positive.

        Example:
            >>> manager = TorqueManager(arbitration_id, dispatcher)
            >>> try:
            ...     data = manager.get_torques_blocking(timeout_ms=500)
            ...     print(f"Current torques: {data.torques}")
            ... except TimeoutError:
            ...     print("Request timed out")
        """
        if timeout_ms <= 0:
            raise ValidationError("timeout_ms must be positive")

        event = threading.Event()
        result_holder: dict[str, TorqueData | None] = {"data": None}

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
            raise TimeoutError(f"No torque data received within {timeout_ms}ms")

    def get_current_torques(self) -> TorqueData | None:
        """Get the most recent cached torque data (non-blocking).

        This method returns the last received torque data (either from set_torques()
        response or get_torques_blocking() response) without sending any new requests.

        Returns:
            TorqueData instance or None if no data received yet.

        Example:
            >>> data = manager.get_current_torques()
            >>> if data:
            ...     age = time.time() - data.timestamp
            ...     if age < 0.1:  # Less than 100ms old
            ...         print(f"Fresh torques: {data.torques}")
        """
        return self._latest_data

    def stream(
        self, interval_ms: float = 100, maxsize: int = 100
    ) -> IterableQueue[TorqueData]:
        """Start streaming mode with periodic torque requests.

        Creates an IterableQueue and starts a background thread that periodically requests
        torque data. Complete data is automatically pushed to the queue.

        The returned queue supports for-loop iteration and blocks when empty (like Go channels).

        Args:
            interval_ms: Request interval in milliseconds (default: 100).
            maxsize: Maximum queue size (default: 100). When full, oldest data is dropped.

        Returns:
            IterableQueue[TorqueData] instance for receiving TorqueData.

        Raises:
            StateError: If streaming is already active.
            ValidationError: If interval_ms is not positive or maxsize is not positive.

        Example:
            >>> manager = TorqueManager(arbitration_id, dispatcher)
            >>> q = manager.stream(interval_ms=100)
            >>> try:
            ...     # Method 1: For-loop iteration (blocks when empty)
            ...     for data in q:
            ...         print(f"Torques: {data.torques}")
            ... finally:
            ...     manager.stop_streaming()
            >>>
            >>> # Method 2: Manual get() calls
            >>> q = manager.stream(interval_ms=100)
            >>> try:
            ...     while True:
            ...         data = q.get(timeout=1.0)
            ...         print(f"Torques: {data.torques}")
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
            target=self._streaming_loop, daemon=True, name="TorqueManager-Streaming"
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
        """Send a torque sensing request via CAN bus.

        Sends a CAN message with data=[0x02] to request current torques.
        """
        msg = can.Message(
            arbitration_id=self._arbitration_id,
            data=self._SENSE_CMD,
            is_extended_id=False,
        )
        self._dispatcher.send(msg)

    def _streaming_loop(self) -> None:
        """Background thread loop for streaming mode.

        Periodically sends torque sensing requests at the configured interval.
        The loop continues until _streaming_timer is set to None by stop_streaming().
        """
        if self._streaming_interval_ms is None:
            raise StateError("Streaming is not active. Call stream() first.")
        while self._streaming_timer is not None:
            self._send_sense_request()
            time.sleep(self._streaming_interval_ms / 1000.0)

    def _on_message(self, msg: can.Message) -> None:
        """Handle incoming CAN messages (callback from dispatcher thread).

        Filters for torque response messages and updates cache or wakes waiters.

        Args:
            msg: CAN message from the bus.

        Note:
            This method executes in the dispatcher's receive thread and must
            return quickly to avoid blocking message reception.
        """
        # Filter: only process messages with correct arbitration ID
        if msg.arbitration_id != self._arbitration_id:
            return

        # Filter: only process torque response messages (start with 0x02)
        if len(msg.data) < 2 or msg.data[0] != self._CONTROL_CMD:
            return

        # Parse torque data (skip first byte which is the command)
        raw_torques = list(msg.data[1:])

        # Validate torque count (should be 6 torques)
        if len(raw_torques) != self._TORQUE_COUNT:
            return

        # Convert from raw CAN format (0-255) to L6Torque (0-100)
        torques = L6Torque.from_raw(raw_torques)

        # Create immutable torque data
        torque_data = TorqueData(torques=torques, timestamp=time.time())

        # Dispatch to all consumers
        self._on_complete_data(torque_data)

    def _on_complete_data(self, data: TorqueData) -> None:
        """Handle complete torque data by dispatching to all consumers.

        This method:
        1. Updates the cached latest data
        2. Wakes up all blocking waiters
        3. Pushes data to the streaming queue (if active)

        Args:
            data: Complete torque data to distribute.

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
