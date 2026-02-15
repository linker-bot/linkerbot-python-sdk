"""Fault management for L20lite robotic hand.

This module provides the FaultManager class for reading joint fault codes
and fault status.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass

import can

from linkerbot.comm import CANMessageDispatcher
from linkerbot.exceptions import ValidationError
from linkerbot.hand.o6.fault import FaultCode
from linkerbot.relay import DataRelay

_JOINT_COUNT = 10


@dataclass(frozen=True)
class L20liteFault:
    """Joint fault codes for L20lite hand.

    Each attribute is a FaultCode enum value representing the fault status
    for that joint. You can directly call methods on each joint's fault code.

    Attributes:
        thumb_flex: Thumb flexion motor fault code
        thumb_abd: Thumb abduction motor fault code
        index_flex: Index finger flexion motor fault code
        middle_flex: Middle finger flexion motor fault code
        ring_flex: Ring finger flexion motor fault code
        pinky_flex: Pinky finger flexion motor fault code
        index_abd: Index finger abduction motor fault code
        ring_abd: Ring finger abduction motor fault code
        pinky_abd: Pinky finger abduction motor fault code
        thumb_yaw: Thumb yaw motor fault code

    Example:
        >>> faults = L20liteFault(...)
        >>> # Check if thumb flex has any fault
        >>> if faults.thumb_flex.has_fault():
        ...     print(f"Thumb flex faults: {faults.thumb_flex.get_fault_names()}")
        >>> # Check all joints
        >>> if faults.has_any_fault():
        ...     print("Some joints have faults")
        >>> # Access via index
        >>> print(faults[0].get_fault_names())  # thumb_flex
    """

    thumb_flex: FaultCode
    thumb_abd: FaultCode
    index_flex: FaultCode
    middle_flex: FaultCode
    ring_flex: FaultCode
    pinky_flex: FaultCode
    index_abd: FaultCode
    ring_abd: FaultCode
    pinky_abd: FaultCode
    thumb_yaw: FaultCode

    def to_list(self) -> list[FaultCode]:
        """Convert to list of FaultCode in joint order.

        Returns:
            List of 10 joint fault codes in order: thumb_flex, thumb_abd,
            index_flex, middle_flex, ring_flex, pinky_flex,
            index_abd, ring_abd, pinky_abd, thumb_yaw
        """
        return [
            self.thumb_flex,
            self.thumb_abd,
            self.index_flex,
            self.middle_flex,
            self.ring_flex,
            self.pinky_flex,
            self.index_abd,
            self.ring_abd,
            self.pinky_abd,
            self.thumb_yaw,
        ]

    @classmethod
    def from_list(cls, values: list[FaultCode]) -> "L20liteFault":
        """Construct from list of FaultCode enum values.

        Args:
            values: List of 10 FaultCode values

        Returns:
            L20liteFault instance

        Raises:
            ValueError: If list doesn't have exactly 10 elements
        """
        if len(values) != _JOINT_COUNT:
            raise ValueError(f"Expected {_JOINT_COUNT} values, got {len(values)}")
        return cls(
            thumb_flex=values[0],
            thumb_abd=values[1],
            index_flex=values[2],
            middle_flex=values[3],
            ring_flex=values[4],
            pinky_flex=values[5],
            index_abd=values[6],
            ring_abd=values[7],
            pinky_abd=values[8],
            thumb_yaw=values[9],
        )

    @classmethod
    def from_raw(cls, values: list[int]) -> "L20liteFault":
        # Internal: Construct from hardware communication format
        if len(values) != _JOINT_COUNT:
            raise ValueError(f"Expected {_JOINT_COUNT} values, got {len(values)}")
        for value in values:
            if value < 0 or value > 255:
                raise ValueError(f"Value {value} out of range [0, 255]")
        # Mask with 0x2F to extract meaningful bits (BIT0-3, BIT5)
        fault_codes = [FaultCode(v & 0x2F) for v in values]
        return cls.from_list(fault_codes)

    def has_any_fault(self) -> bool:
        """Check if any joint has a fault.

        Returns:
            True if any joint has a fault, False otherwise.

        Example:
            >>> faults = L20liteFault(...)
            >>> if faults.has_any_fault():
            ...     print("At least one joint has a fault")
        """
        return any(code.has_fault() for code in self.to_list())

    def __getitem__(self, index: int) -> FaultCode:
        """Support indexing: faults[0] returns thumb_flex.

        Args:
            index: Joint index (0-9)

        Returns:
            Joint fault code value

        Raises:
            IndexError: If index is out of range
        """
        return self.to_list()[index]

    def __len__(self) -> int:
        """Return number of joints (always 10 for L20lite)."""
        return _JOINT_COUNT


@dataclass(frozen=True)
class FaultData:
    """Immutable fault data container.

    Attributes:
        faults: L20liteFault instance containing fault codes for all joints.
        timestamp: Unix timestamp when the data was received.
    """

    faults: L20liteFault
    timestamp: float


class FaultManager:
    """Manager for joint fault management.

    This class provides two access modes for fault operations:
    1. Blocking mode: get_blocking() - request and wait for all 10 fault codes
    2. Cache reading: get_snapshot() - non-blocking read of cached faults
    """

    _FRAME_MAP: dict[int, list[str]] = {
        0x35: [
            "thumb_flex",
            "thumb_abd",
            "index_flex",
            "middle_flex",
            "ring_flex",
        ],
        0x36: ["pinky_flex", "index_abd", "ring_abd", "pinky_abd", "thumb_yaw"],
    }

    def __init__(self, arbitration_id: int, dispatcher: CANMessageDispatcher) -> None:
        """Initialize the fault manager.

        Args:
            arbitration_id: CAN arbitration ID for fault operations.
            dispatcher: CAN message dispatcher to use for communication.
        """
        self._arbitration_id = arbitration_id
        self._dispatcher = dispatcher
        self._dispatcher.subscribe(self._on_message)
        self._relay = DataRelay[FaultData]()
        self._pending: dict[int, list[FaultCode]] = {}
        self._in_flight = False
        self._in_flight_since: float = 0

    def get_blocking(self, timeout_ms: float = 100) -> FaultData:
        """Request and wait for current joint fault codes (blocking).

        This method sends a read request and blocks until
        all 10 fault codes are received or the timeout expires.

        Args:
            timeout_ms: Maximum time to wait in milliseconds (default: 100).

        Returns:
            FaultData instance containing faults and timestamp.

        Raises:
            TimeoutError: If no response is received within timeout.
            ValidationError: If timeout_ms is not positive.

        Example:
            >>> data = manager.get_blocking(timeout_ms=500)
            >>> if data.faults.has_any_fault():
            ...     print(f"Thumb flex: {data.faults.thumb_flex.get_fault_names()}")
        """
        if timeout_ms <= 0:
            raise ValidationError("timeout_ms must be positive")
        self._pending.clear()
        self._in_flight = False
        self._send_sense_request()
        return self._relay.wait(timeout_ms / 1000.0)

    def get_snapshot(self) -> FaultData | None:
        """Get the most recent cached fault data (non-blocking).

        Returns:
            FaultData instance or None if no data received yet.

        Example:
            >>> data = manager.get_snapshot()
            >>> if data:
            ...     print(f"Has faults: {data.faults.has_any_fault()}")
        """
        return self._relay.snapshot()

    def _set_event_sink(self, sink: Callable[[FaultData], None]) -> None:
        self._relay.set_sink(sink)

    _IN_FLIGHT_TIMEOUT_S = 0.2

    def _send_sense_request(self) -> None:
        if (
            self._in_flight
            and (time.monotonic() - self._in_flight_since) < self._IN_FLIGHT_TIMEOUT_S
        ):
            return
        self._in_flight = True
        self._in_flight_since = time.monotonic()
        self._pending.clear()
        for cmd in self._FRAME_MAP:
            msg = can.Message(
                arbitration_id=self._arbitration_id,
                data=[cmd],
                is_extended_id=False,
            )
            self._dispatcher.send(msg)

    def _on_message(self, msg: can.Message) -> None:
        if msg.arbitration_id != self._arbitration_id:
            return

        if len(msg.data) < 2:
            return

        cmd = msg.data[0]
        if cmd not in self._FRAME_MAP:
            return

        expected_fields = self._FRAME_MAP[cmd]
        raw_codes = list(msg.data[1:])

        if len(raw_codes) != len(expected_fields):
            return

        decoded = [FaultCode(v & 0x2F) for v in raw_codes]
        self._pending[cmd] = decoded

        # Check if all frames have been received
        if set(self._pending.keys()) != set(self._FRAME_MAP.keys()):
            return

        # All frames received — merge into L20liteFault
        kwargs: dict[str, FaultCode] = {}
        for frame_cmd, fields in self._FRAME_MAP.items():
            for field, value in zip(fields, self._pending[frame_cmd]):
                kwargs[field] = value

        faults = L20liteFault(**kwargs)
        fault_data = FaultData(faults=faults, timestamp=time.time())
        self._in_flight = False
        self._pending.clear()
        self._relay.push(fault_data)
