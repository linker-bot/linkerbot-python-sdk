"""Tests for L20Lite lifecycle management with hardware."""

import os
from typing import Literal, cast

import pytest

from linkerbot import L20lite
from linkerbot.exceptions import StateError

pytestmark = [pytest.mark.l20lite, pytest.mark.lifecycle]


class TestLifecycle:
    """Test L20lite instance lifecycle (context manager, close, post-close behavior)."""

    def test_context_manager_creates_usable_instance(self, l20lite_hand: L20lite):
        """Within a context-managed block the hand should be open and usable."""
        assert not l20lite_hand.is_closed(), (
            "Hand should not be closed inside context manager"
        )

    def test_context_manager_closes_on_exit(self):
        """After exiting the `with` block the hand should be closed."""
        interface = os.environ.get("CAN_INTERFACE", "can0")
        side = cast(Literal["left", "right"], os.environ.get("L20LITE_SIDE", "left"))

        with L20lite(side=side, interface_name=interface) as hand:
            assert not hand.is_closed(), "Hand should be open inside context manager"

        assert hand.is_closed(), "Hand should be closed after exiting context manager"

    def test_closed_hand_is_closed(self, closed_hand: L20lite):
        """A hand returned from closed_hand fixture should be closed."""
        assert closed_hand.is_closed()

    def test_close_is_idempotent(self, closed_hand: L20lite):
        """Calling close() multiple times on a closed hand should not raise."""
        closed_hand.close()
        closed_hand.close()
        closed_hand.close()

    def test_get_blocking_after_close_raises(self, closed_hand: L20lite):
        """get_blocking on a closed hand should raise StateError."""
        with pytest.raises((StateError, Exception)):
            closed_hand.angle.get_blocking()

    def test_start_polling_after_close_raises(self, closed_hand: L20lite):
        """start_polling on a closed hand should raise StateError."""
        with pytest.raises((StateError, Exception)):
            closed_hand.start_polling()

    def test_stream_after_close_raises(self, closed_hand: L20lite):
        """stream() on a closed hand should raise StateError."""
        with pytest.raises((StateError, Exception)):
            closed_hand.stream()
