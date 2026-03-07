"""Tests for A7 arm lifecycle management with hardware."""

import os
import time
from typing import Literal, cast

import pytest

from linkerbot.arm import A7

pytestmark = [pytest.mark.a7, pytest.mark.lifecycle]

NUM_JOINTS = 7


class TestLifecycle:
    """Test A7 instance lifecycle (create, stop, post-stop behavior)."""

    def test_create_instance_is_usable(self):
        """Newly created instance should return valid angles via get_angles."""
        interface = os.environ.get("CAN_INTERFACE", "can0")
        side = cast(Literal["left", "right"], os.environ.get("ARM_SIDE", "left"))

        arm = A7(side=side, interface_name=interface)
        try:
            angles = arm.get_angles()
            assert angles is not None, "get_angles should not return None"
            assert len(angles) == NUM_JOINTS, (
                f"Expected {NUM_JOINTS} joints, got {len(angles)}"
            )
        finally:
            arm.close()

    def test_stop_does_not_raise(self):
        """Calling stop() on a live instance should not raise."""
        interface = os.environ.get("CAN_INTERFACE", "can0")
        side = cast(Literal["left", "right"], os.environ.get("ARM_SIDE", "left"))

        arm = A7(side=side, interface_name=interface)
        arm.close()

    def test_stop_is_idempotent(self):
        """Calling stop() multiple times should not raise."""
        interface = os.environ.get("CAN_INTERFACE", "can0")
        side = cast(Literal["left", "right"], os.environ.get("ARM_SIDE", "left"))

        arm = A7(side=side, interface_name=interface)
        arm.close()
        time.sleep(0.2)
        arm.close()
        arm.close()

    def test_operations_after_stop_raise(self):
        """Commands that send CAN messages on a stopped arm should raise.

        After stop(), the CAN dispatcher is shut down (running=False).
        Calling enable() → reset_error() → motor._send() → dispatcher.send()
        raises RuntimeError("Cannot send on a stopped CANMessageDispatcher").
        Note: read-only accessors like get_angles() return cached values and
        do NOT raise; this test uses enable() which performs a CAN write.
        """
        interface = os.environ.get("CAN_INTERFACE", "can0")
        side = cast(Literal["left", "right"], os.environ.get("ARM_SIDE", "left"))

        arm = A7(side=side, interface_name=interface)
        arm.close()

        with pytest.raises(Exception):
            arm.enable()

    def test_stop_in_finally_does_not_raise(self):
        """stop() called in finally block should never raise (idempotent guard)."""
        interface = os.environ.get("CAN_INTERFACE", "can0")
        side = cast(Literal["left", "right"], os.environ.get("ARM_SIDE", "left"))

        arm = A7(side=side, interface_name=interface)
        try:
            arm.close()
        finally:
            arm.close()
