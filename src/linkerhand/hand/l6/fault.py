"""Fault management for L6 robotic hand.

This module provides the FaultManager class for clearing joint fault codes
via CAN bus communication.
"""

import can

from linkerhand.comm import CANMessageDispatcher
from linkerhand.exceptions import ValidationError


class FaultManager:
    """Manager for clearing joint fault codes.

    Use clear_faults() to clear fault codes for one or more joints.
    """

    _CLEAR_FAULT_CMD = 0x83
    _JOINT_COUNT = 6

    def __init__(self, arbitration_id: int, dispatcher: CANMessageDispatcher) -> None:
        """Initialize the fault manager.

        Args:
            arbitration_id: CAN arbitration ID for fault commands.
            dispatcher: CAN message dispatcher to use for communication.
        """
        self._arbitration_id = arbitration_id
        self._dispatcher = dispatcher

    def clear_faults(
        self,
        joints: tuple[int, ...] | list[int] | None = None,
        all: bool = False,
    ) -> None:
        """Clear fault codes for selected joints.

        Args:
            joints: Tuple or list of 6 values (0 or 1) indicating which joint faults to clear.
                    Ignored when all=True.
            all: If True, clear faults for all joints (one-click clear all).

        Raises:
            ValidationError: If all=False and joints is not provided, or
                        if joints count is not 6 or values are not 0/1 integers.
        """
        if all:
            joints = (1, 1, 1, 1, 1, 1)
        elif joints is None:
            raise ValidationError("Must provide joints or set all=True")

        if len(joints) != self._JOINT_COUNT:
            raise ValidationError(
                f"Expected {self._JOINT_COUNT} joint flags, got {len(joints)}"
            )

        for i, value in enumerate(joints):
            if not isinstance(value, int):
                raise ValidationError(f"Joint {i} flag must be int, got {type(value)}")
            if value not in (0, 1):
                raise ValidationError(f"Joint {i} flag value {value} must be 0 or 1")

        data = [self._CLEAR_FAULT_CMD, *joints]
        msg = can.Message(
            arbitration_id=self._arbitration_id,
            data=data,
            is_extended_id=False,
        )
        self._dispatcher.send(msg)
