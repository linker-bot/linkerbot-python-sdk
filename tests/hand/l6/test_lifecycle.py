"""Tests for L6 lifecycle management with hardware."""

import os
from typing import Literal, cast

import pytest

from linkerbot import L6

pytestmark = [pytest.mark.l6, pytest.mark.lifecycle]


class TestLifecycle:
    """Test L6 instance lifecycle (context manager, close, post-close behavior)."""

    def test_context_manager_creates_usable_instance(self, l6_hand: L6):
        """Within a context-managed block the hand should be open and usable."""
        assert not l6_hand.is_closed(), (
            "Hand should not be closed inside context manager"
        )

    def test_context_manager_closes_on_exit(self):
        """After exiting the `with` block the hand should be closed."""
        interface = os.environ.get("CAN_INTERFACE", "can0")
        side = cast(Literal["left", "right"], os.environ.get("L6_SIDE", "left"))

        with L6(side=side, interface_name=interface) as hand:
            assert not hand.is_closed(), "Hand should be open inside context manager"

        assert hand.is_closed(), "Hand should be closed after exiting context manager"

    def test_close_is_idempotent(self):
        """Calling close() multiple times should not raise."""
        interface = os.environ.get("CAN_INTERFACE", "can0")
        side = cast(Literal["left", "right"], os.environ.get("L6_SIDE", "left"))

        with L6(side=side, interface_name=interface) as hand:
            pass

        # Close again several times -- none should raise
        hand.close()
        hand.close()
        hand.close()

    def test_operations_after_close_raise(self, closed_hand: L6):
        """Operations on a closed hand should raise an exception."""
        with pytest.raises(Exception):
            closed_hand.angle.get_blocking()
