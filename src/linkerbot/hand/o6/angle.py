"""Angle control and sensing for O6 robotic hand.

This module provides the AngleManager class for controlling joint angles
and reading angle sensor data via CAN bus communication.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass

import can

from linkerbot.comm import CANMessageDispatcher
from linkerbot.exceptions import ValidationError
from linkerbot.relay import DataRelay


@dataclass
class O6Angle:
    """Joint angles for O6 hand (0-100 range).

    Attributes:
        thumb_flex: Thumb flexion joint angle (0-100). Higher values extend the finger.
        thumb_abd: Thumb abduction joint angle (0-100). Higher values move away from palm.
        index: Index finger flexion joint angle (0-100). Higher values extend the finger.
        middle: Middle finger flexion joint angle (0-100). Higher values extend the finger.
        ring: Ring finger flexion joint angle (0-100). Higher values extend the finger.
        pinky: Pinky finger flexion joint angle (0-100). Higher values extend the finger.
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
            List of 6 joint angles [thumb_flex, thumb_abd, index, middle, ring, pinky]
        """
        return [
            self.thumb_flex,
            self.thumb_abd,
            self.index,
            self.middle,
            self.ring,
            self.pinky,
        ]

    def to_raw(self) -> list[int]:
        # Internal: Convert to hardware communication format
        return [round(v * 255 / 100) for v in self.to_list()]

    @classmethod
    def from_list(cls, values: list[float]) -> "O6Angle":
        """Construct from list of floats (0-100 range).

        Args:
            values: List of 6 float values in 0-100 range

        Returns:
            O6Angle instance

        Raises:
            ValueError: If list doesn't have exactly 6 elements
        """
        if len(values) != 6:
            raise ValueError(f"Expected 6 values, got {len(values)}")
        for value in values:
            if not isinstance(value, (float, int)):
                raise ValueError(f"Angle value {value} must be float/int")
            if not 0 <= value <= 100:
                raise ValueError(f"Angle value {value} out of range [0, 100]")
        return cls(
            thumb_flex=values[0],
            thumb_abd=values[1],
            index=values[2],
            middle=values[3],
            ring=values[4],
            pinky=values[5],
        )

    @classmethod
    def from_raw(cls, values: list[int]) -> "O6Angle":
        # Internal: Construct from hardware communication format
        if len(values) != 6:
            raise ValueError(f"Expected 6 values, got {len(values)}")
        for value in values:
            if value < 0 or value > 255:
                raise ValueError(f"Value {value} out of range [0, 255]")
        normalized = [v * 100 / 255 for v in values]
        return cls.from_list(normalized)

    def __getitem__(self, index: int) -> float:
        """Support indexing: angles[0] returns thumb_flex.

        Args:
            index: Joint index (0-5)

        Returns:
            Joint angle value

        Raises:
            IndexError: If index is out of range
        """
        return self.to_list()[index]

    def __len__(self) -> int:
        """Return number of joints (always 6 for O6)."""
        return 6


@dataclass(frozen=True)
class AngleData:
    """Immutable angle data container.

    Attributes:
        angles: O6Angle instance containing joint angles (0-100 range).
        timestamp: Unix timestamp when the data was received.
    """

    angles: O6Angle
    timestamp: float


class AngleManager:
    """Manager for joint angle control and sensing.

    This class provides three access modes for angle operations:
    1. Angle control: set_angles() - send 6 target angles and cache response
    2. Blocking mode: get_blocking() - request and wait for 6 current angles
    3. Cache reading: get_snapshot() - non-blocking read of cached angles
    """

    _CONTROL_CMD = 0x01
    _SENSE_CMD = [0x01]
    _ANGLE_COUNT = 6

    def __init__(self, arbitration_id: int, dispatcher: CANMessageDispatcher) -> None:
        """Initialize the angle manager.

        Args:
            arbitration_id: CAN arbitration ID for angle control/sensing.
            dispatcher: CAN message dispatcher to use for communication.
        """
        self._arbitration_id = arbitration_id
        self._dispatcher = dispatcher
        self._dispatcher.subscribe(self._on_message)
        self._relay = DataRelay[AngleData]()

    def set_angles(self, angles: O6Angle | list[float]) -> None:
        """Send target angles to the robotic hand.

        This method sends 6 target angles to the hand. The hand will respond
        with the current angles, which are automatically cached and can be
        retrieved via get_snapshot().

        Args:
            angles: O6Angle instance or list of 6 target angles (range 0-100 each).

        Raises:
            ValidationError: If angles count is not 6 or values are out of range.

        Example:
            >>> manager = AngleManager(arbitration_id, dispatcher)
            >>> manager.set_angles(O6Angle(thumb_flex=50.0, thumb_abd=30.0,
            ...                            index=60.0, middle=60.0, ring=60.0, pinky=60.0))
            >>> manager.set_angles([50.0, 30.0, 60.0, 60.0, 60.0, 60.0])
        """
        if isinstance(angles, O6Angle):
            raw_angles = angles.to_raw()
        elif isinstance(angles, list):
            raw_angles = O6Angle.from_list(angles).to_raw()
        else:
            raise ValidationError(
                f"Expected O6Angle or list, got {type(angles).__name__}"
            )

        # Build and send message
        data = [self._CONTROL_CMD, *raw_angles]
        msg = can.Message(
            arbitration_id=self._arbitration_id,
            data=data,
            is_extended_id=False,
        )
        self._dispatcher.send(msg)

    def get_blocking(self, timeout_ms: float = 100) -> AngleData:
        """Request and wait for current joint angles (blocking).

        This method sends a sensing request and blocks until 6 current angles
        are received or the timeout expires.

        Args:
            timeout_ms: Maximum time to wait in milliseconds (default: 100).

        Returns:
            AngleData instance containing angles and timestamp.

        Raises:
            TimeoutError: If no response is received within timeout.
            ValidationError: If timeout_ms is not positive.

        Example:
            >>> data = manager.get_blocking(timeout_ms=500)
            >>> print(f"Current angles: {data.angles}")
        """
        if timeout_ms <= 0:
            raise ValidationError("timeout_ms must be positive")
        self._send_sense_request()
        return self._relay.wait(timeout_ms / 1000.0)

    def get_snapshot(self) -> AngleData | None:
        """Get the most recent cached angle data (non-blocking).

        Returns:
            AngleData instance or None if no data received yet.

        Example:
            >>> data = manager.get_snapshot()
            >>> if data:
            ...     print(f"Fresh angles: {data.angles}")
        """
        return self._relay.snapshot()

    def _set_event_sink(self, sink: Callable[[AngleData], None]) -> None:
        self._relay.set_sink(sink)

    def _send_sense_request(self) -> None:
        msg = can.Message(
            arbitration_id=self._arbitration_id,
            data=self._SENSE_CMD,
            is_extended_id=False,
        )
        self._dispatcher.send(msg)

    def _on_message(self, msg: can.Message) -> None:
        # Filter: only process messages with correct arbitration ID
        if msg.arbitration_id != self._arbitration_id:
            return

        # Filter: only process angle response messages (start with 0x01)
        if len(msg.data) < 2 or msg.data[0] != self._CONTROL_CMD:
            return

        # Parse angle data (skip first byte which is the command)
        raw_angles = list(msg.data[1:])

        # Validate angle count (should be 6 angles)
        if len(raw_angles) != self._ANGLE_COUNT:
            return

        angles = O6Angle.from_raw(raw_angles)
        angle_data = AngleData(angles=angles, timestamp=time.time())
        self._relay.push(angle_data)
