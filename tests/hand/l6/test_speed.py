"""Tests for L6 SpeedManager with hardware."""

import pytest

from linkerbot import L6
from linkerbot.hand.l6 import L6Speed
from tests.conftest import InteractiveSession
from tests.hand.l6.conftest import move_and_wait

pytestmark = [pytest.mark.l6, pytest.mark.control]


class TestSpeedManagerSet:
    """Test SpeedManager set_speeds method."""

    def test_set_speeds_with_list(self, l6_hand: L6):
        """set_speeds should accept a list of floats without error."""
        l6_hand.speed.set_speeds([50.0] * 6)

    def test_set_speeds_with_l6speed(self, l6_hand: L6):
        """set_speeds should accept an L6Speed instance without error."""
        l6_hand.speed.set_speeds(
            L6Speed(
                thumb_flex=50.0,
                thumb_abd=50.0,
                index=50.0,
                middle=50.0,
                ring=50.0,
                pinky=50.0,
            )
        )

    def test_set_different_speeds(self, l6_hand: L6):
        """set_speeds should accept different per-motor speeds without error."""
        l6_hand.speed.set_speeds([20.0, 40.0, 60.0, 80.0, 100.0, 50.0])


@pytest.mark.interactive
class TestSpeedInteractive:
    """Interactive tests for verifying speed affects movement."""

    def test_speed_affects_movement(
        self, l6_hand: L6, interactive_session: InteractiveSession
    ):
        """Verify that speed settings visibly affect finger movement speed."""
        session = interactive_session

        session.step(
            instruction="Setting LOW speed [10]*6 then closing fingers",
            action=lambda: (
                l6_hand.speed.set_speeds([10.0] * 6),
                move_and_wait(l6_hand, [0.0, 100.0, 0.0, 0.0, 0.0, 0.0], wait_sec=4.0),
            ),
            expected="Fingers move slowly",
        )

        session.step(
            instruction="Setting HIGH speed [100]*6 then opening fingers",
            action=lambda: (
                l6_hand.speed.set_speeds([100.0] * 6),
                move_and_wait(l6_hand, [100.0] * 6, wait_sec=2.0),
            ),
            expected="Fingers move fast",
        )

        session.step(
            instruction="Setting HIGH speed [100]*6 then closing fingers",
            action=lambda: (
                l6_hand.speed.set_speeds([100.0] * 6),
                move_and_wait(l6_hand, [0.0, 100.0, 0.0, 0.0, 0.0, 0.0], wait_sec=2.0),
            ),
            expected="Clearly faster than the first step",
        )

        session.run()
        session.save_report()

        if session.quit_early:
            pytest.exit("Tester quit early")

        failed = session.failed_steps()
        if failed:
            pytest.fail(
                f"{len(failed)} step(s) failed: "
                + "; ".join(s.instruction for s in failed)
            )
