"""Fault management for L25 robotic hand.

This module provides the FaultManager class for reading joint fault codes,
fault status, and clearing faults. L25 has 16 degrees of freedom split
across five CAN frames (0x59-0x5D), one per finger.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Flag

import can

from linkerbot.comm import CANMessageDispatcher
from linkerbot.exceptions import ValidationError
from linkerbot.relay import DataRelay

_JOINT_COUNT = 16


class L25FaultCode(Flag):
    """Motor fault code flags for L25 hand.

    Each bit represents a specific fault condition:
    - BIT0 (1): Motor rotor lock
    - BIT1 (2): Motor overcurrent
    - BIT2 (4): Motor stall fault
    - BIT3 (8): Voltage abnormal
    - BIT4 (16): Self-check abnormal
    - BIT5 (32): Overtemperature
    - BIT6 (64): Soft rotor lock
    - BIT7 (128): Motor communication abnormal
    """

    NONE = 0
    MOTOR_ROTOR_LOCK = 1 << 0  # BIT0: Motor rotor lock
    MOTOR_OVER_CURRENT = 1 << 1  # BIT1: Motor overcurrent
    MOTOR_STALL_FAULT = 1 << 2  # BIT2: Motor stall fault
    VOLTAGE_ABNORMAL = 1 << 3  # BIT3: Voltage abnormal
    SELF_CHECK_ABNORMAL = 1 << 4  # BIT4: Self-check abnormal
    OVER_TEMPERATURE = 1 << 5  # BIT5: Overtemperature
    SOFT_ROTOR_LOCK = 1 << 6  # BIT6: Soft rotor lock
    MOTOR_COMM_ABNORMAL = 1 << 7  # BIT7: Motor communication abnormal

    def has_fault(self) -> bool:
        """Check if this fault code has any fault.

        Returns:
            True if any fault bit is set, False otherwise.

        Example:
            >>> code = L25FaultCode.MOTOR_ROTOR_LOCK | L25FaultCode.OVER_TEMPERATURE
            >>> code.has_fault()
            True
            >>> L25FaultCode.NONE.has_fault()
            False
        """
        return self != L25FaultCode.NONE

    def get_fault_names(self) -> list[str]:
        """Get human-readable fault names for this fault code.

        Returns:
            List of fault names. Returns ["No faults"] if no faults are present.

        Example:
            >>> code = L25FaultCode.MOTOR_ROTOR_LOCK | L25FaultCode.OVER_TEMPERATURE
            >>> code.get_fault_names()
            ['Motor rotor lock', 'Overtemperature']
            >>> L25FaultCode.NONE.get_fault_names()
            ['No faults']
        """
        if not self.has_fault():
            return ["No faults"]

        names: list[str] = []
        if self & L25FaultCode.MOTOR_ROTOR_LOCK:
            names.append("Motor rotor lock")
        if self & L25FaultCode.MOTOR_OVER_CURRENT:
            names.append("Motor overcurrent")
        if self & L25FaultCode.MOTOR_STALL_FAULT:
            names.append("Motor stall fault")
        if self & L25FaultCode.VOLTAGE_ABNORMAL:
            names.append("Voltage abnormal")
        if self & L25FaultCode.SELF_CHECK_ABNORMAL:
            names.append("Self-check abnormal")
        if self & L25FaultCode.OVER_TEMPERATURE:
            names.append("Overtemperature")
        if self & L25FaultCode.SOFT_ROTOR_LOCK:
            names.append("Soft rotor lock")
        if self & L25FaultCode.MOTOR_COMM_ABNORMAL:
            names.append("Motor communication abnormal")
        return names


@dataclass(frozen=True)
class L25Fault:
    """Joint fault codes for L25 hand.

    Each attribute is an L25FaultCode enum value representing the fault status
    for that joint. You can directly call methods on each joint's fault code.

    Attributes:
        thumb_abd: Thumb abduction motor fault code
        thumb_yaw: Thumb yaw motor fault code
        thumb_root1: Thumb root1 motor fault code
        thumb_tip: Thumb tip motor fault code
        index_abd: Index finger abduction motor fault code
        index_root1: Index finger root1 motor fault code
        index_tip: Index finger tip motor fault code
        middle_abd: Middle finger abduction motor fault code
        middle_root1: Middle finger root1 motor fault code
        middle_tip: Middle finger tip motor fault code
        ring_abd: Ring finger abduction motor fault code
        ring_root1: Ring finger root1 motor fault code
        ring_tip: Ring finger tip motor fault code
        pinky_abd: Pinky finger abduction motor fault code
        pinky_root1: Pinky finger root1 motor fault code
        pinky_tip: Pinky finger tip motor fault code

    Example:
        >>> faults = L25Fault(...)
        >>> # Check if thumb yaw has any fault
        >>> if faults.thumb_abd.has_fault():
        ...     print(f"Thumb abd faults: {faults.thumb_abd.get_fault_names()}")
        >>> # Check all joints
        >>> if faults.has_any_fault():
        ...     print("Some joints have faults")
        >>> # Access via index
        >>> print(faults[0].get_fault_names())  # thumb_abd
    """

    thumb_abd: L25FaultCode
    thumb_yaw: L25FaultCode
    thumb_root1: L25FaultCode
    thumb_tip: L25FaultCode
    index_abd: L25FaultCode
    index_root1: L25FaultCode
    index_tip: L25FaultCode
    middle_abd: L25FaultCode
    middle_root1: L25FaultCode
    middle_tip: L25FaultCode
    ring_abd: L25FaultCode
    ring_root1: L25FaultCode
    ring_tip: L25FaultCode
    pinky_abd: L25FaultCode
    pinky_root1: L25FaultCode
    pinky_tip: L25FaultCode

    def to_list(self) -> list[L25FaultCode]:
        """Convert to list of L25FaultCode in joint order.

        Returns:
            List of 16 joint fault codes in order: thumb_abd, thumb_yaw,
            thumb_root1, thumb_tip, index_abd, index_root1, index_tip,
            middle_abd, middle_root1, middle_tip, ring_abd, ring_root1,
            ring_tip, pinky_abd, pinky_root1, pinky_tip
        """
        return [
            self.thumb_abd,
            self.thumb_yaw,
            self.thumb_root1,
            self.thumb_tip,
            self.index_abd,
            self.index_root1,
            self.index_tip,
            self.middle_abd,
            self.middle_root1,
            self.middle_tip,
            self.ring_abd,
            self.ring_root1,
            self.ring_tip,
            self.pinky_abd,
            self.pinky_root1,
            self.pinky_tip,
        ]

    @classmethod
    def from_list(cls, values: list[L25FaultCode]) -> "L25Fault":
        """Construct from list of L25FaultCode enum values.

        Args:
            values: List of 16 L25FaultCode values

        Returns:
            L25Fault instance

        Raises:
            ValueError: If list doesn't have exactly 16 elements
        """
        if len(values) != _JOINT_COUNT:
            raise ValueError(f"Expected {_JOINT_COUNT} values, got {len(values)}")
        return cls(
            thumb_abd=values[0],
            thumb_yaw=values[1],
            thumb_root1=values[2],
            thumb_tip=values[3],
            index_abd=values[4],
            index_root1=values[5],
            index_tip=values[6],
            middle_abd=values[7],
            middle_root1=values[8],
            middle_tip=values[9],
            ring_abd=values[10],
            ring_root1=values[11],
            ring_tip=values[12],
            pinky_abd=values[13],
            pinky_root1=values[14],
            pinky_tip=values[15],
        )

    @classmethod
    def from_raw(cls, values: list[int]) -> "L25Fault":
        # Internal: Construct from hardware communication format
        if len(values) != _JOINT_COUNT:
            raise ValueError(f"Expected {_JOINT_COUNT} values, got {len(values)}")
        for value in values:
            if value < 0 or value > 255:
                raise ValueError(f"Value {value} out of range [0, 255]")
        fault_codes = [L25FaultCode(v) for v in values]
        return cls.from_list(fault_codes)

    def has_any_fault(self) -> bool:
        """Check if any joint has a fault.

        Returns:
            True if any joint has a fault, False otherwise.

        Example:
            >>> faults = L25Fault(...)
            >>> if faults.has_any_fault():
            ...     print("At least one joint has a fault")
        """
        return any(code.has_fault() for code in self.to_list())

    def __getitem__(self, index: int) -> L25FaultCode:
        """Support indexing: faults[0] returns thumb_abd (abduction).

        Args:
            index: Joint index (0-15)

        Returns:
            Joint fault code value

        Raises:
            IndexError: If index is out of range
        """
        return self.to_list()[index]

    def __len__(self) -> int:
        """Return number of joints (always 16 for L25)."""
        return _JOINT_COUNT


@dataclass(frozen=True)
class FaultData:
    """Immutable fault data container.

    Attributes:
        faults: L25Fault instance containing fault codes for all joints.
        timestamp: Unix timestamp when the data was received.
    """

    faults: L25Fault
    timestamp: float


class FaultManager:
    """Manager for joint fault management.

    L25 splits 16 joints across five CAN frames, one per finger:
    - 0x59: thumb (abd, yaw, root1, reserve, reserve, tip)
    - 0x5A: index (abd, reserve, root1, reserve, reserve, tip)
    - 0x5B: middle (abd, reserve, root1, reserve, reserve, tip)
    - 0x5C: ring (abd, reserve, root1, reserve, reserve, tip)
    - 0x5D: pinky (abd, reserve, root1, reserve, reserve, tip)

    Each frame is 7 bytes: [cmd, abd, yaw/reserve, root1, reserve, reserve, tip].
    Reserved positions (None in the map) are ignored on decode.

    This class provides three access modes for fault operations:
    1. Blocking mode: get_blocking() - request and wait for all 16 fault codes
    2. Cache reading: get_snapshot() - non-blocking read of cached faults
    3. Fault clearing: clear_faults() - clear all joint faults
    """

    _FRAME_MAP: dict[int, list[str | None]] = {
        0x59: ["thumb_abd", "thumb_yaw", "thumb_root1", None, None, "thumb_tip"],
        0x5A: ["index_abd", None, "index_root1", None, None, "index_tip"],
        0x5B: ["middle_abd", None, "middle_root1", None, None, "middle_tip"],
        0x5C: ["ring_abd", None, "ring_root1", None, None, "ring_tip"],
        0x5D: ["pinky_abd", None, "pinky_root1", None, None, "pinky_tip"],
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
        self._pending: dict[int, list[L25FaultCode]] = {}
        self._in_flight = False
        self._in_flight_since: float = 0

    def get_blocking(self, timeout_ms: float = 100) -> FaultData:
        """Request and wait for current joint fault codes (blocking).

        This method sends sense requests for all five frames and blocks until
        all 16 fault codes are received or the timeout expires.

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
            ...     print(f"Thumb abd: {data.faults.thumb_abd.get_fault_names()}")
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

    def clear_faults(self) -> None:
        """Clear fault codes for all joints (fire-and-forget).

        Sends a clear command to each finger frame. Each clear message
        sets all 6 data positions to 1 to request fault clearing.

        Example:
            >>> manager = FaultManager(arbitration_id, dispatcher)
            >>> manager.clear_faults()
        """
        for cmd in self._FRAME_MAP:
            data = [cmd, 1, 1, 1, 1, 1, 1]
            msg = can.Message(
                arbitration_id=self._arbitration_id,
                data=data,
                is_extended_id=False,
            )
            self._dispatcher.send(msg)

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

        decoded = [L25FaultCode(v) for v in raw_codes]
        self._pending[cmd] = decoded

        # Check if all frames have been received
        if set(self._pending.keys()) != set(self._FRAME_MAP.keys()):
            return

        # All frames received -- merge into L25Fault
        kwargs: dict[str, L25FaultCode] = {}
        for frame_cmd, fields in self._FRAME_MAP.items():
            for field, value in zip(fields, self._pending[frame_cmd]):
                if field is not None:
                    kwargs[field] = value

        faults = L25Fault(**kwargs)
        fault_data = FaultData(faults=faults, timestamp=time.time())
        self._in_flight = False
        self._pending.clear()
        self._relay.push(fault_data)
