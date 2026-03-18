"""Force sensor data acquisition for L25 robotic hand.

This module provides force sensor management for the L25 robotic hand:

- SingleForceSensorManager: Manages a single finger's force sensor.
- ForceSensorManager: Manages all 5 fingers' force sensors (thumb, index, middle, ring, pinky).
"""

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

import can
import numpy as np
import numpy.typing as npt

from linkerbot.comm import CANMessageDispatcher
from linkerbot.exceptions import TimeoutError, ValidationError
from linkerbot.relay import DataRelay


@dataclass(frozen=True)
class ForceSensorData:
    """Immutable force sensor data container.

    Attributes:
        values: NumPy array of shape (12, 6) with dtype uint8 representing force sensor readings.
                Each row corresponds to a frame, and each frame contains 6 bytes.
        timestamp: Unix timestamp when the data was assembled.
    """

    values: npt.NDArray[np.uint8]
    timestamp: float


@dataclass(frozen=True)
class AllFingersData:
    """Immutable container for complete hand force sensor data from all 5 fingers.

    Attributes:
        thumb: Force sensor data from the thumb.
        index: Force sensor data from the index finger.
        middle: Force sensor data from the middle finger.
        ring: Force sensor data from the ring finger.
        pinky: Force sensor data from the pinky finger.
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

    def add_frame(self, frame_id: int, data: bytes) -> "FrameBatch":
        new_frames = {**self.frames, frame_id: data}
        return FrameBatch(frames=new_frames)

    def is_complete(self) -> bool:
        return len(self.frames) == 12

    def assemble(self) -> ForceSensorData:
        data = bytearray(72)
        for i in range(12):
            data[i * 6 : (i + 1) * 6] = self.frames[i]
        return ForceSensorData(
            values=np.array(data, dtype=np.uint8).reshape(12, 6), timestamp=time.time()
        )


class SingleForceSensorManager:
    """Manager for a single finger's force sensor data acquisition.

    This class provides two access modes for force sensor operations:
    1. Blocking mode: get_blocking() - wait for next complete data with timeout
    2. Cache mode: get_snapshot() - non-blocking read of most recent data
    """

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
            command_prefix: Command prefix for the sensor.
        """
        self._arbitration_id = arbitration_id
        self._command_prefix = command_prefix
        self._request_cmd = [command_prefix, 0xC6]

        self._dispatcher = dispatcher
        self._dispatcher.subscribe(self._on_message)

        # Frame assembly state
        self._frame_batch: FrameBatch | None = None
        self._in_flight = False
        self._in_flight_since: float = 0

        self._relay = DataRelay[ForceSensorData]()

    def get_blocking(self, timeout_ms: float = 1000) -> ForceSensorData:
        """Get force sensor data with blocking wait.

        This method registers a waiter and blocks until complete sensor data
        is received or the timeout expires.

        Args:
            timeout_ms: Maximum time to wait in milliseconds (default: 1000).

        Returns:
            Complete force sensor data.

        Raises:
            TimeoutError: If no complete data is received within timeout.
            ValidationError: If timeout_ms is not positive.

        Example:
            >>> data = manager.get_blocking(timeout_ms=500)
            >>> print(f"Received {len(data.values)} bytes")
        """
        if timeout_ms <= 0:
            raise ValidationError("timeout_ms must be positive")
        self._frame_batch = None
        self._in_flight = False
        self._send_request()
        return self._relay.wait(timeout_ms / 1000.0)

    def get_snapshot(self) -> ForceSensorData | None:
        """Get the most recent cached sensor data (non-blocking).

        Returns:
            Latest ForceSensorData or None if no data received yet.

        Example:
            >>> data = manager.get_snapshot()
            >>> if data:
            ...     print("Data is available")
        """
        return self._relay.snapshot()

    def _set_event_sink(self, sink: Callable[[ForceSensorData], None]) -> None:
        self._relay.set_sink(sink)

    _IN_FLIGHT_TIMEOUT_S = 0.2

    def _send_request(self) -> None:
        if (
            self._in_flight
            and (time.monotonic() - self._in_flight_since) < self._IN_FLIGHT_TIMEOUT_S
        ):
            return
        self._in_flight = True
        self._in_flight_since = time.monotonic()
        self._frame_batch = None
        msg = can.Message(
            arbitration_id=self._arbitration_id,
            data=self._request_cmd,
            is_extended_id=False,
        )
        self._dispatcher.send(msg)

    def _on_message(self, msg: can.Message) -> None:
        # Filter: only process messages with correct arbitration ID
        if msg.arbitration_id != self._arbitration_id:
            return

        # Filter: only process sensor response frames
        if len(msg.data) < 8 or msg.data[0] != self._command_prefix:
            return

        # Extract frame information
        frame_idx = msg.data[1] >> 4  # Extract high nibble: 0-11
        frame_data = bytes(msg.data[2:8])  # 6 bytes of payload

        # Validate frame index
        if frame_idx >= self._FRAME_COUNT:
            return

        # Frame 0 starts a new batch, discarding any incomplete old one
        if frame_idx == 0:
            self._frame_batch = FrameBatch()
        elif self._frame_batch is None:
            return

        self._frame_batch = self._frame_batch.add_frame(frame_idx, frame_data)

        # Check if we have all frames
        if self._frame_batch.is_complete():
            complete_data = self._frame_batch.assemble()
            self._in_flight = False
            self._frame_batch = None
            self._relay.push(complete_data)


class ForceSensorManager:
    """Manager for all finger force sensors on the L25 robotic hand.

    This class manages force sensors for all 5 fingers (thumb, index, middle, ring, pinky)
    and provides unified access to sensor data from all fingers.
    """

    _MCU_INTER_REQUEST_DELAY_S = (
        0.0025  # 2.5ms - MCU can only handle one finger at a time
    )

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

        # Event sink for unified stream
        self._event_sink: Callable[[AllFingersData], None] | None = None
        self._sink_latest: dict[str, ForceSensorData] = {}
        self._sink_updated: set[str] = set()

    def get_blocking(self, timeout_ms: float = 1000) -> AllFingersData:
        """Get force sensor data for all fingers with blocking wait.

        All 5 fingers are queried sequentially. Each finger's request is sent
        only after the previous finger's complete response is received, ensuring
        the MCU is idle before each new request.

        Args:
            timeout_ms: Maximum total time to wait in milliseconds (default: 1000).

        Returns:
            AllFingersData containing force sensor data from all 5 fingers.

        Raises:
            TimeoutError: If any finger fails to respond within timeout.
            ValidationError: If timeout_ms is not positive.

        Example:
            >>> all_data = manager.get_blocking(timeout_ms=500)
            >>> print(f"Thumb force: {all_data.thumb.values[0]}")
        """
        if timeout_ms <= 0:
            raise ValidationError("timeout_ms must be positive")

        deadline = time.monotonic() + timeout_ms / 1000.0
        results: dict[str, ForceSensorData] = {}

        for name, sensor in self._fingers.items():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                missing = set(self._fingers) - set(results)
                raise TimeoutError(f"Force sensor timeout for: {', '.join(missing)}")
            results[name] = sensor.get_blocking(timeout_ms=remaining * 1000)

        return AllFingersData(
            thumb=results["thumb"],
            index=results["index"],
            middle=results["middle"],
            ring=results["ring"],
            pinky=results["pinky"],
        )

    def get_snapshot(self) -> AllFingersData | None:
        """Get the most recent cached sensor data for all fingers (non-blocking).

        Returns AllFingersData only when all 5 fingers have data.
        Returns None if any finger has no data yet.

        Returns:
            AllFingersData or None if not all fingers have data.

        Example:
            >>> data = manager.get_snapshot()
            >>> if data:
            ...     print(f"Thumb: {data.thumb.values.shape}")
        """
        thumb = self._fingers["thumb"].get_snapshot()
        index = self._fingers["index"].get_snapshot()
        middle = self._fingers["middle"].get_snapshot()
        ring = self._fingers["ring"].get_snapshot()
        pinky = self._fingers["pinky"].get_snapshot()
        if (
            thumb is None
            or index is None
            or middle is None
            or ring is None
            or pinky is None
        ):
            return None
        return AllFingersData(
            thumb=thumb,
            index=index,
            middle=middle,
            ring=ring,
            pinky=pinky,
        )

    def get_finger(self, name: str) -> SingleForceSensorManager:
        """Get the SingleForceSensorManager for a specific finger.

        Args:
            name: Finger name ('thumb', 'index', 'middle', 'ring', 'pinky').

        Returns:
            SingleForceSensorManager for the specified finger.

        Raises:
            KeyError: If finger name is invalid.
        """
        return self._fingers[name]

    def _set_event_sink(self, sink: Callable[[AllFingersData], None]) -> None:
        self._event_sink = sink
        self._sink_latest = {}
        self._sink_updated = set()
        for name, sensor in self._fingers.items():
            sensor._set_event_sink(lambda data, n=name: self._on_finger_data(n, data))

    def _on_finger_data(self, name: str, data: ForceSensorData) -> None:
        self._sink_latest[name] = data
        self._sink_updated.add(name)
        if len(self._sink_updated) == len(self._fingers):
            snapshot = AllFingersData(
                thumb=self._sink_latest["thumb"],
                index=self._sink_latest["index"],
                middle=self._sink_latest["middle"],
                ring=self._sink_latest["ring"],
                pinky=self._sink_latest["pinky"],
            )
            self._sink_updated = set()
            if self._event_sink is not None:
                self._event_sink(snapshot)

    def _send_sense_request(self) -> None:
        finger_list = list(self._fingers.values())
        for i, sensor in enumerate(finger_list):
            if i > 0:
                time.sleep(self._MCU_INTER_REQUEST_DELAY_S)
            sensor._send_request()
