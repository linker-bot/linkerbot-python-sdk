"""Speed and acceleration control for O6 robotic hand.

This module provides the SpeedManager and AccelerationManager classes for
controlling motor speeds and accelerations via CAN bus communication.
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
class O6Speed:
    """Motor speeds for O6 hand (0-100 range or RPM).

    Speeds can be specified either as normalized 0-100 values or in RPM units.
    Maximum speed: 186.66 RPM (corresponds to 100).

    Attributes:
        thumb_flex: Thumb flexion motor speed (0-100). Higher values = faster.
        thumb_abd: Thumb abduction motor speed (0-100). Higher values = faster.
        index: Index finger motor speed (0-100). Higher values = faster.
        middle: Middle finger motor speed (0-100). Higher values = faster.
        ring: Ring finger motor speed (0-100). Higher values = faster.
        pinky: Pinky finger motor speed (0-100). Higher values = faster.
    """

    thumb_flex: float
    thumb_abd: float
    index: float
    middle: float
    ring: float
    pinky: float

    # Hardware conversion constant: 1 hardware unit = 0.732 RPM
    _RPM_PER_UNIT: float = 0.732
    _MAX_RPM: float = 255 * _RPM_PER_UNIT  # 186.66 RPM

    def to_list(self) -> list[float]:
        """Convert to list of floats in joint order.

        Returns:
            List of 6 motor speeds [thumb_flex, thumb_abd, index, middle, ring, pinky]
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
    def from_list(cls, values: list[float]) -> "O6Speed":
        """Construct from list of floats (0-100 range).

        Args:
            values: List of 6 float values in 0-100 range

        Returns:
            O6Speed instance

        Raises:
            ValueError: If list doesn't have exactly 6 elements
        """
        if len(values) != 6:
            raise ValueError(f"Expected 6 values, got {len(values)}")
        for value in values:
            if value < 0 or value > 100:
                raise ValueError(f"Value {value} out of range [0, 100]")
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
        # Use round() for better precision and clamp to valid range [0, 255]
        return [max(0, min(255, round(v * 255 / 100))) for v in self.to_list()]

    @classmethod
    def from_raw(cls, values: list[int]) -> "O6Speed":
        # Internal: Construct from hardware communication format
        if len(values) != 6:
            raise ValueError(f"Expected 6 values, got {len(values)}")
        for value in values:
            if value < 0 or value > 255:
                raise ValueError(f"Value {value} out of range [0, 255]")
        normalized = [v * 100 / 255 for v in values]
        return cls.from_list(normalized)

    def to_rpm(self) -> list[float]:
        """Convert to list of speeds in RPM units.

        Returns:
            List of 6 motor speeds in RPM [thumb_flex, thumb_abd, index, middle, ring, pinky]

        Example:
            >>> speed = O6Speed(50.0, 50.0, 50.0, 50.0, 50.0, 50.0)
            >>> rpm_values = speed.to_rpm()
            >>> print(rpm_values[0])  # ~93.33 RPM
        """
        return [v * self._MAX_RPM / 100 for v in self.to_list()]

    @classmethod
    def from_rpm(cls, rpm_values: list[float]) -> "O6Speed":
        """Construct from list of speeds in RPM units.

        Args:
            rpm_values: List of 6 speed values in RPM (0 to 186.66 RPM)

        Returns:
            O6Speed instance

        Raises:
            ValueError: If list doesn't have exactly 6 elements or values are out of range.

        Example:
            >>> # Set all motors to 90 RPM
            >>> speed = O6Speed.from_rpm([90.0, 90.0, 90.0, 90.0, 90.0, 90.0])
            >>> # Set different speeds per motor
            >>> speed = O6Speed.from_rpm([100.0, 80.0, 120.0, 120.0, 120.0, 120.0])
        """
        if len(rpm_values) != 6:
            raise ValueError(f"Expected 6 values, got {len(rpm_values)}")

        # Validate RPM values
        for i, rpm in enumerate(rpm_values):
            if rpm < 0 or rpm > cls._MAX_RPM:
                raise ValueError(
                    f"RPM value {i} ({rpm}) out of range [0, {cls._MAX_RPM:.2f}]"
                )

        # Convert RPM to 0-100 range
        normalized = [rpm * 100 / cls._MAX_RPM for rpm in rpm_values]
        return cls.from_list(normalized)

    def __getitem__(self, index: int) -> float:
        """Support indexing: speeds[0] returns thumb_flex.

        Args:
            index: Joint index (0-5)

        Returns:
            Motor speed value

        Raises:
            IndexError: If index is out of range
        """
        return self.to_list()[index]

    def __len__(self) -> int:
        """Return number of motors (always 6 for O6)."""
        return 6


@dataclass(frozen=True)
class SpeedData:
    """Immutable speed data container.

    Attributes:
        speeds: O6Speed instance containing motor speeds (0-100 range).
        timestamp: Unix timestamp when the data was received.
    """

    speeds: O6Speed
    timestamp: float


class SpeedManager:
    """Manager for motor speed control and sensing.

    This class provides four access modes for speed operations:
    1. Speed control: set_speeds() - send 6 target speeds and cache response
    2. Blocking mode: get_speeds_blocking() - request and wait for 6 current speeds
    3. Streaming mode: stream() - continuous polling with Queue-based delivery
    4. Cache reading: get_current_speeds() - non-blocking read of cached speeds
    """

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
        self._streaming_queue: IterableQueue[SpeedData] | None = None
        self._streaming_timer: threading.Thread | None = None
        self._streaming_interval_ms: float | None = None

    def set_speeds(self, speeds: O6Speed | list[float]) -> None:
        """Send target speeds to the robotic hand motors.

        This method sends 6 target speeds to the hand.

        Args:
            speeds: O6Speed instance or list of 6 target speeds (range 0-100 each).

        Raises:
            ValidationError: If speeds count is not 6 or values are out of range.

        Example:
            >>> manager = SpeedManager(arbitration_id, dispatcher)
            >>> # Using O6Speed instance with normalized values (0-100)
            >>> manager.set_speeds(O6Speed(thumb_flex=50.0, thumb_abd=50.0,
            ...                            index=50.0, middle=50.0, ring=50.0, pinky=50.0))
            >>> # Using list with normalized values (0-100)
            >>> manager.set_speeds([50.0, 50.0, 50.0, 50.0, 50.0, 50.0])
            >>> # Using actual RPM units
            >>> manager.set_speeds(O6Speed.from_rpm([90.0, 90.0, 120.0, 120.0, 120.0, 120.0]))
        """
        if isinstance(speeds, O6Speed):
            raw_speeds = speeds.to_raw()
        elif isinstance(speeds, list):
            raw_speeds = O6Speed.from_list(speeds).to_raw()

        # Build and send message
        data = [self._CONTROL_CMD, *raw_speeds]
        msg = can.Message(
            arbitration_id=self._arbitration_id,
            data=data,
            is_extended_id=False,
        )
        self._dispatcher.send(msg)

    def get_speeds_blocking(self, timeout_ms: float = 100) -> SpeedData:
        """Request and wait for current motor speeds (blocking).

        This method sends a sensing request and blocks until 6 current speeds
        are received or the timeout expires. If streaming mode is active, this
        method may receive data from streaming requests.

        Args:
            timeout_ms: Maximum time to wait in milliseconds (default: 100).

        Returns:
            SpeedData instance containing speeds and timestamp.

        Raises:
            TimeoutError: If no response is received within timeout.
            ValidationError: If timeout_ms is not positive.

        Example:
            >>> manager = SpeedManager(arbitration_id, dispatcher)
            >>> try:
            ...     data = manager.get_speeds_blocking(timeout_ms=500)
            ...     print(f"Current speeds: {data.speeds}")
            ... except TimeoutError:
            ...     print("Request timed out")
        """
        if timeout_ms <= 0:
            raise ValidationError("timeout_ms must be positive")

        event = threading.Event()
        result_holder: dict[str, SpeedData | None] = {"data": None}

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

    def get_current_speeds(self) -> SpeedData | None:
        """Get the most recent cached speed data (non-blocking).

        This method returns the last received speed data (either from set_speeds()
        response or get_speeds_blocking() response) without sending any new requests.

        Returns:
            SpeedData instance or None if no data received yet.

        Example:
            >>> data = manager.get_current_speeds()
            >>> if data:
            ...     age = time.time() - data.timestamp
            ...     if age < 0.1:  # Less than 100ms old
            ...         print(f"Fresh speeds: {data.speeds}")
        """
        return self._latest_data

    def stream(
        self, interval_ms: float = 100, maxsize: int = 100
    ) -> IterableQueue[SpeedData]:
        """Start streaming mode with periodic speed requests.

        Creates an IterableQueue and starts a background thread that periodically requests
        speed data. Complete data is automatically pushed to the queue.

        The returned queue supports for-loop iteration and blocks when empty (like Go channels).

        Args:
            interval_ms: Request interval in milliseconds (default: 100).
            maxsize: Maximum queue size (default: 100). When full, oldest data is dropped.

        Returns:
            IterableQueue[SpeedData] instance for receiving SpeedData.

        Raises:
            StateError: If streaming is already active.
            ValidationError: If interval_ms is not positive or maxsize is not positive.

        Example:
            >>> manager = SpeedManager(arbitration_id, dispatcher)
            >>> q = manager.stream(interval_ms=100)
            >>> try:
            ...     # Method 1: For-loop iteration (blocks when empty)
            ...     for data in q:
            ...         print(f"Speeds: {data.speeds}")
            ... finally:
            ...     manager.stop_streaming()
            >>>
            >>> # Method 2: Manual get() calls
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
        self._streaming_queue = IterableQueue(maxsize=maxsize)
        self._streaming_interval_ms = interval_ms

        # Start background thread for periodic requests
        self._streaming_timer = threading.Thread(
            target=self._streaming_loop, daemon=True, name="SpeedManager-Streaming"
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
            data=self._SENSE_CMD,
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

        # Filter: only process speed response messages (start with 0x05)
        if len(msg.data) < 2 or msg.data[0] != self._CONTROL_CMD:
            return

        # Parse speed data (skip first byte which is the command)
        raw_speeds = list(msg.data[1:])

        # Validate speed count (should be 6 speeds)
        if len(raw_speeds) != self._SPEED_COUNT:
            return

        speeds = O6Speed.from_raw(raw_speeds)
        speed_data = SpeedData(speeds=speeds, timestamp=time.time())
        self._on_complete_data(speed_data)

    def _on_complete_data(self, data: SpeedData) -> None:
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


@dataclass
class O6Acceleration:
    """Motor accelerations for O6 hand (0-100 range or deg/s²).

    Accelerations can be specified either as normalized 0-100 values or in deg/s² units.
    Maximum acceleration: 2209.8 deg/s² (corresponds to 100).

    Attributes:
        thumb_flex: Thumb flexion motor acceleration (0-100). Higher values = faster acceleration.
        thumb_abd: Thumb abduction motor acceleration (0-100). Higher values = faster acceleration.
        index: Index finger motor acceleration (0-100). Higher values = faster acceleration.
        middle: Middle finger motor acceleration (0-100). Higher values = faster acceleration.
        ring: Ring finger motor acceleration (0-100). Higher values = faster acceleration.
        pinky: Pinky finger motor acceleration (0-100). Higher values = faster acceleration.
    """

    thumb_flex: float
    thumb_abd: float
    index: float
    middle: float
    ring: float
    pinky: float

    # Hardware conversion constant: 1 hardware unit = 8.7 deg/s²
    _DEG_PER_SEC2_PER_UNIT: float = 8.7
    _MAX_DEG_PER_SEC2: float = 254 * _DEG_PER_SEC2_PER_UNIT  # 2209.8 deg/s²

    def to_list(self) -> list[float]:
        """Convert to list of floats in joint order.

        Returns:
            List of 6 motor accelerations [thumb_flex, thumb_abd, index, middle, ring, pinky]
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
    def from_list(cls, values: list[float]) -> "O6Acceleration":
        """Construct from list of floats (0-100 range).

        Args:
            values: List of 6 float values in 0-100 range

        Returns:
            O6Acceleration instance

        Raises:
            ValueError: If list doesn't have exactly 6 elements
        """
        if len(values) != 6:
            raise ValueError(f"Expected 6 values, got {len(values)}")
        for value in values:
            if value < 0 or value > 100:
                raise ValueError(f"Value {value} out of range [0, 100]")
        return cls(
            thumb_flex=values[0],
            thumb_abd=values[1],
            index=values[2],
            middle=values[3],
            ring=values[4],
            pinky=values[5],
        )

    def to_raw(self) -> list[int]:
        # Internal: Convert to hardware communication format with special mapping
        # User sees 0-100 where 100 is max acceleration
        # Hardware has special mapping:
        #   - 0 = maximum acceleration (special value)
        #   - 1-254 = increasing acceleration (1 is min, 254 is near-max)
        # Mapping:
        #   - User 100 -> Hardware 0 (special case for maximum)
        #   - User 0-99 -> Hardware 1-254 (linear increasing)
        def convert_single(v: float) -> int:
            if v >= 100:
                return 0  # Maximum acceleration
            else:
                # Map 0-99 linearly to 1-254
                # v=0 -> 1, v=99 -> 254
                result = round(1 + v * 253 / 99)
                return max(1, min(254, result))  # Clamp to [1, 254]

        return [convert_single(v) for v in self.to_list()]

    @classmethod
    def from_raw(cls, values: list[int]) -> "O6Acceleration":
        # Internal: Construct from hardware communication format with special mapping
        # Hardware to user mapping:
        #   - Hardware 0 -> User 100 (special case)
        #   - Hardware 1-254 -> User 0-99 (linear increasing)
        if len(values) != 6:
            raise ValueError(f"Expected 6 values, got {len(values)}")
        for value in values:
            if value < 0 or value > 254:
                raise ValueError(f"Value {value} out of range [0, 254]")

        def convert_single(v: int) -> float:
            if v == 0:
                return 100.0  # Maximum acceleration
            else:
                # Map 1-254 to 0-99
                # hw=1 -> 0, hw=254 -> 99
                return (v - 1) * 99 / 253

        normalized = [convert_single(v) for v in values]
        return cls.from_list(normalized)

    def to_deg_per_sec2(self) -> list[float]:
        """Convert to list of accelerations in deg/s² units.

        Returns:
            List of 6 motor accelerations in deg/s² [thumb_flex, thumb_abd, index, middle, ring, pinky]

        Example:
            >>> accel = O6Acceleration(50.0, 50.0, 50.0, 50.0, 50.0, 50.0)
            >>> deg_s2_values = accel.to_deg_per_sec2()
            >>> print(deg_s2_values[0])  # ~1104.9 deg/s²
        """
        return [v * self._MAX_DEG_PER_SEC2 / 100 for v in self.to_list()]

    @classmethod
    def from_deg_per_sec2(cls, deg_per_sec2_values: list[float]) -> "O6Acceleration":
        """Construct from list of accelerations in deg/s² units.

        Args:
            deg_per_sec2_values: List of 6 acceleration values in deg/s² (0 to 2209.8 deg/s²)

        Returns:
            O6Acceleration instance

        Raises:
            ValueError: If list doesn't have exactly 6 elements or values are out of range.

        Example:
            >>> # Set all motors to 1000 deg/s²
            >>> accel = O6Acceleration.from_deg_per_sec2([1000.0] * 6)
            >>> # Set different accelerations per motor
            >>> accel = O6Acceleration.from_deg_per_sec2([1500.0, 1200.0, 1800.0, 1800.0, 1800.0, 1800.0])
        """
        if len(deg_per_sec2_values) != 6:
            raise ValueError(f"Expected 6 values, got {len(deg_per_sec2_values)}")

        # Validate acceleration values
        for i, acc in enumerate(deg_per_sec2_values):
            if acc < 0 or acc > cls._MAX_DEG_PER_SEC2:
                raise ValueError(
                    f"Acceleration value {i} ({acc}) out of range [0, {cls._MAX_DEG_PER_SEC2:.2f}]"
                )

        # Convert deg/s² to 0-100 range
        normalized = [acc * 100 / cls._MAX_DEG_PER_SEC2 for acc in deg_per_sec2_values]
        return cls.from_list(normalized)

    def __getitem__(self, index: int) -> float:
        """Support indexing: accelerations[0] returns thumb_flex.

        Args:
            index: Joint index (0-5)

        Returns:
            Motor acceleration value

        Raises:
            IndexError: If index is out of range
        """
        return self.to_list()[index]

    def __len__(self) -> int:
        """Return number of motors (always 6 for O6)."""
        return 6


@dataclass(frozen=True)
class AccelerationData:
    """Immutable acceleration data container.

    Attributes:
        accelerations: O6Acceleration instance containing motor accelerations (0-100 range).
        timestamp: Unix timestamp when the data was received.
    """

    accelerations: O6Acceleration
    timestamp: float


class AccelerationManager:
    """Manager for motor acceleration control and sensing.

    This class provides four access modes for acceleration operations:
    1. Acceleration control: set_accelerations() - send 6 target accelerations and cache response
    2. Blocking mode: get_accelerations_blocking() - request and wait for 6 current accelerations
    3. Streaming mode: stream() - continuous polling with Queue-based delivery
    4. Cache reading: get_current_accelerations() - non-blocking read of cached accelerations
    """

    _CONTROL_CMD = 0x87
    _SENSE_CMD = [0x87]
    _ACCELERATION_COUNT = 6

    def __init__(self, arbitration_id: int, dispatcher: CANMessageDispatcher) -> None:
        """Initialize the acceleration manager.

        Args:
            arbitration_id: CAN arbitration ID for acceleration control/sensing.
            dispatcher: CAN message dispatcher to use for communication.
        """
        self._arbitration_id = arbitration_id
        self._dispatcher = dispatcher
        self._dispatcher.subscribe(self._on_message)

        # Latest acceleration data cache
        self._latest_data: AccelerationData | None = None

        # Blocking mode support
        self._blocking_waiters: list[tuple[threading.Event, dict]] = []
        self._waiters_lock = threading.Lock()

        # Streaming mode support
        self._streaming_queue: IterableQueue[AccelerationData] | None = None
        self._streaming_timer: threading.Thread | None = None
        self._streaming_interval_ms: float | None = None

    def set_accelerations(self, accelerations: O6Acceleration | list[float]) -> None:
        """Send target accelerations to the robotic hand motors.

        This method sends 6 target accelerations to the hand.

        Args:
            accelerations: O6Acceleration instance or list of 6 target accelerations
                (range 0-100 each, where 100 is maximum acceleration).

        Raises:
            ValidationError: If accelerations count is not 6 or values are out of range.

        Example:
            >>> manager = AccelerationManager(arbitration_id, dispatcher)
            >>> # Using O6Acceleration instance with normalized values (0-100)
            >>> manager.set_accelerations(O6Acceleration(thumb_flex=80.0, thumb_abd=80.0,
            ...                                          index=80.0, middle=80.0,
            ...                                          ring=80.0, pinky=80.0))
            >>> # Using list with normalized values (0-100)
            >>> manager.set_accelerations([80.0, 80.0, 80.0, 80.0, 80.0, 80.0])
            >>> # Using actual deg/s² units
            >>> manager.set_accelerations(O6Acceleration.from_deg_per_sec2([1500.0] * 6))
        """
        if isinstance(accelerations, O6Acceleration):
            raw_accelerations = accelerations.to_raw()
        elif isinstance(accelerations, list):
            # Validate input
            if len(accelerations) != self._ACCELERATION_COUNT:
                raise ValidationError(
                    f"Expected {self._ACCELERATION_COUNT} accelerations, got {len(accelerations)}"
                )
            # Validate acceleration values (0-100 range)
            for i, acceleration in enumerate(accelerations):
                if not isinstance(acceleration, float):
                    raise ValidationError(
                        f"Acceleration {i} must be float, got {type(acceleration)}"
                    )
            raw_accelerations = O6Acceleration.from_list(accelerations).to_raw()

        # Build and send message
        data = [self._CONTROL_CMD, *raw_accelerations]
        msg = can.Message(
            arbitration_id=self._arbitration_id,
            data=data,
            is_extended_id=False,
        )
        self._dispatcher.send(msg)

    def get_accelerations_blocking(self, timeout_ms: float = 100) -> AccelerationData:
        """Request and wait for current motor accelerations (blocking).

        This method sends a sensing request and blocks until 6 current accelerations
        are received or the timeout expires. If streaming mode is active, this
        method may receive data from streaming requests.

        Args:
            timeout_ms: Maximum time to wait in milliseconds (default: 100).

        Returns:
            AccelerationData instance containing accelerations and timestamp.

        Raises:
            TimeoutError: If no response is received within timeout.
            ValidationError: If timeout_ms is not positive.

        Example:
            >>> manager = AccelerationManager(arbitration_id, dispatcher)
            >>> try:
            ...     data = manager.get_accelerations_blocking(timeout_ms=500)
            ...     print(f"Current accelerations: {data.accelerations}")
            ... except TimeoutError:
            ...     print("Request timed out")
        """
        if timeout_ms <= 0:
            raise ValidationError("timeout_ms must be positive")

        event = threading.Event()
        result_holder: dict[str, AccelerationData | None] = {"data": None}

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
            raise TimeoutError(f"No acceleration data received within {timeout_ms}ms")

    def get_current_accelerations(self) -> AccelerationData | None:
        """Get the most recent cached acceleration data (non-blocking).

        This method returns the last received acceleration data (either from set_accelerations()
        response or get_accelerations_blocking() response) without sending any new requests.

        Returns:
            AccelerationData instance or None if no data received yet.

        Example:
            >>> data = manager.get_current_accelerations()
            >>> if data:
            ...     age = time.time() - data.timestamp
            ...     if age < 0.1:  # Less than 100ms old
            ...         print(f"Fresh accelerations: {data.accelerations}")
        """
        return self._latest_data

    def stream(
        self, interval_ms: float = 100, maxsize: int = 100
    ) -> IterableQueue[AccelerationData]:
        """Start streaming mode with periodic acceleration requests.

        Creates an IterableQueue and starts a background thread that periodically requests
        acceleration data. Complete data is automatically pushed to the queue.

        The returned queue supports for-loop iteration and blocks when empty (like Go channels).

        Args:
            interval_ms: Request interval in milliseconds (default: 100).
            maxsize: Maximum queue size (default: 100). When full, oldest data is dropped.

        Returns:
            IterableQueue[AccelerationData] instance for receiving AccelerationData.

        Raises:
            StateError: If streaming is already active.
            ValidationError: If interval_ms is not positive or maxsize is not positive.

        Example:
            >>> manager = AccelerationManager(arbitration_id, dispatcher)
            >>> q = manager.stream(interval_ms=100)
            >>> try:
            ...     # Method 1: For-loop iteration (blocks when empty)
            ...     for data in q:
            ...         print(f"Accelerations: {data.accelerations}")
            ... finally:
            ...     manager.stop_streaming()
            >>>
            >>> # Method 2: Manual get() calls
            >>> q = manager.stream(interval_ms=100)
            >>> try:
            ...     while True:
            ...         data = q.get(timeout=1.0)
            ...         print(f"Accelerations: {data.accelerations}")
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
            name="AccelerationManager-Streaming",
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
            data=self._SENSE_CMD,
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

        # Filter: only process acceleration response messages (start with 0x87)
        if len(msg.data) < 2 or msg.data[0] != self._CONTROL_CMD:
            return

        # Parse acceleration data (skip first byte which is the command)
        raw_accelerations = list(msg.data[1:])

        # Validate acceleration count (should be 6 accelerations)
        if len(raw_accelerations) != self._ACCELERATION_COUNT:
            return

        accelerations = O6Acceleration.from_raw(raw_accelerations)
        acceleration_data = AccelerationData(
            accelerations=accelerations, timestamp=time.time()
        )
        self._on_complete_data(acceleration_data)

    def _on_complete_data(self, data: AccelerationData) -> None:
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
