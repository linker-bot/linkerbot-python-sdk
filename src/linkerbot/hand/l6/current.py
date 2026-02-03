"""Current sensing for L6 robotic hand.

This module provides the CurrentManager class for reading motor current
sensor data via CAN bus communication.
"""

import queue
import threading
import time
from dataclasses import dataclass

import can

from linkerbot.comm import CANMessageDispatcher
from linkerbot.exceptions import StateError, TimeoutError, ValidationError
from linkerbot.queue import IterableQueue


@dataclass
class L6Current:
    """Motor currents for L6 hand in milliamps (mA).

    Attributes:
        thumb_flex: Thumb flexion motor current in mA
        thumb_abd: Thumb abduction motor current in mA
        index: Index finger motor current in mA
        middle: Middle finger motor current in mA
        ring: Ring finger motor current in mA
        pinky: Pinky finger motor current in mA
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
            List of 6 currents [thumb_flex, thumb_abd, index, middle, ring, pinky]
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
    def from_list(cls, values: list[float]) -> "L6Current":
        """Construct from list of floats in milliamps.

        Args:
            values: List of 6 float values in mA

        Returns:
            L6Current instance

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

    def to_raw(self) -> list[int]:
        # Internal: Convert to hardware communication format
        return [int(v * 255 / 1400) for v in self.to_list()]

    @classmethod
    def from_raw(cls, values: list[int]) -> "L6Current":
        # Internal: Construct from hardware communication format
        if len(values) != 6:
            raise ValueError(f"Expected 6 values, got {len(values)}")
        currents_mA = [v * 1400 / 255 for v in values]
        return cls.from_list(currents_mA)

    def __getitem__(self, index: int) -> float:
        """Support indexing: currents[0] returns thumb_flex.

        Args:
            index: Joint index (0-5)

        Returns:
            Current value

        Raises:
            IndexError: If index is out of range
        """
        return self.to_list()[index]

    def __len__(self) -> int:
        """Return number of current sensors (always 6 for L6)."""
        return 6


@dataclass(frozen=True)
class CurrentData:
    """Immutable current data container.

    Attributes:
        currents: L6Current instance containing motor currents in milliamps (mA).
        timestamp: Unix timestamp when the data was received.
    """

    currents: L6Current
    timestamp: float


class CurrentManager:
    """Manager for motor current sensing.

    This class provides three access modes for current operations:
    1. Blocking mode: get_currents_blocking() - request and wait for 6 currents
    2. Streaming mode: stream() - continuous polling with Queue-based delivery
    3. Cache reading: get_current_currents() - non-blocking read of cached currents
    """

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
        msg = can.Message(
            arbitration_id=self._arbitration_id,
            data=self._SENSE_CMD_DATA,
            is_extended_id=False,
        )
        self._dispatcher.send(msg)

    def _streaming_loop(self) -> None:
        if self._streaming_interval_ms is None:
            raise StateError("Streaming is not active. Call stream() first.")
        while self._streaming_timer is not None:
            self._send_sense_request()
            time.sleep(self._streaming_interval_ms / 1000.0)

    def _on_message(self, msg: can.Message) -> None:
        # Filter: only process messages with correct arbitration ID
        if msg.arbitration_id != self._arbitration_id:
            return

        # Filter: only process current response messages (start with 0x36)
        if len(msg.data) < 2 or msg.data[0] != self._SENSE_CMD:
            return

        # Parse current data (skip first byte which is the command)
        raw_currents = list(msg.data[1:])

        # Validate current count (should be 6 currents)
        if len(raw_currents) != self._CURRENT_COUNT:
            return

        currents = L6Current.from_raw(raw_currents)
        current_data = CurrentData(currents=currents, timestamp=time.time())
        self._on_complete_data(current_data)

    def _on_complete_data(self, data: CurrentData) -> None:
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
