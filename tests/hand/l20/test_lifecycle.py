"""Tests for L20 lifecycle management with hardware."""

import os
from typing import Literal, cast

import pytest

from linkerbot import L20

pytestmark = [pytest.mark.l20, pytest.mark.lifecycle]


class TestLifecycle:
    """Test L20 instance lifecycle (context manager, close, post-close behavior)."""

    def test_context_manager_creates_usable_instance(self, l20_hand: L20):
        """Within a context-managed block the hand should be open and usable."""
        assert not l20_hand.is_closed(), (
            "Hand should not be closed inside context manager"
        )

    def test_context_manager_closes_on_exit(self):
        """After exiting the `with` block the hand should be closed."""
        interface = os.environ.get("CAN_INTERFACE", "can0")
        side = cast(Literal["left", "right"], os.environ.get("L20_SIDE", "left"))

        with L20(side=side, interface_name=interface) as hand:
            assert not hand.is_closed(), "Hand should be open inside context manager"

        assert hand.is_closed(), "Hand should be closed after exiting context manager"

    def test_close_is_idempotent(self):
        """Calling close() multiple times should not raise."""
        interface = os.environ.get("CAN_INTERFACE", "can0")
        side = cast(Literal["left", "right"], os.environ.get("L20_SIDE", "left"))

        with L20(side=side, interface_name=interface) as hand:
            pass

        # Close again several times -- none should raise
        hand.close()
        hand.close()
        hand.close()

    def test_operations_after_close_raise(self, closed_hand: L20):
        """Operations on a closed hand should raise an exception."""
        with pytest.raises(RuntimeError, match="stopped CANMessageDispatcher"):
            closed_hand.angle.get_blocking()
