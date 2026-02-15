"""Tests for L20Lite SpeedManager with hardware."""

import pytest

from linkerbot import L20lite
from linkerbot.hand.l20lite import L20liteSpeed
from tests.conftest import InteractiveSession
from tests.hand.l20lite.conftest import move_and_wait

pytestmark = [pytest.mark.l20lite, pytest.mark.control]


class TestSpeedManagerSet:
    """Test SpeedManager set_speeds method."""

    def test_set_speeds_with_list(self, l20lite_hand: L20lite):
        """set_speeds should accept a list of floats without error."""
        l20lite_hand.speed.set_speeds([50.0] * 10)

    def test_set_speeds_with_l20lite_speed(self, l20lite_hand: L20lite):
        """set_speeds should accept an L20liteSpeed instance without error."""
        l20lite_hand.speed.set_speeds(
            L20liteSpeed(
                thumb_flex=50.0,
                thumb_abd=100.0,
                index_flex=50.0,
                middle_flex=50.0,
                ring_flex=50.0,
                pinky_flex=50.0,
                index_abd=50.0,
                ring_abd=50.0,
                pinky_abd=50.0,
                thumb_yaw=100.0,
            )
        )

    def test_set_different_speeds(self, l20lite_hand: L20lite):
        """set_speeds should accept different per-motor speeds without error."""
        l20lite_hand.speed.set_speeds(
            [20.0, 40.0, 60.0, 80.0, 100.0, 50.0, 30.0, 70.0, 90.0, 10.0]
        )


class TestSpeedManagerBlocking:
    """Test SpeedManager blocking read."""

    def test_get_blocking_returns_valid_data(self, l20lite_hand: L20lite):
        """Blocking read should return 10 speed values."""
        data = l20lite_hand.speed.get_blocking(timeout_ms=500)

        assert data is not None
        assert len(data.speeds) == 10

    def test_get_blocking_has_timestamp(self, l20lite_hand: L20lite):
        """Speed data should have a valid timestamp."""
        data = l20lite_hand.speed.get_blocking(timeout_ms=500)

        assert data.timestamp > 0


@pytest.mark.interactive
class TestSpeedInteractive:
    """Interactive tests for verifying speed affects movement."""

    def test_speed_affects_movement(
        self, l20lite_hand: L20lite, interactive_session: InteractiveSession
    ):
        """Verify that speed settings visibly affect finger movement speed."""
        session = interactive_session

        session.step(
            instruction="Setting LOW speed [10]*10 then closing fingers",
            action=lambda: (
                l20lite_hand.speed.set_speeds([10.0] * 10),
                move_and_wait(
                    l20lite_hand,
                    [0.0, 100.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 100],
                    wait_sec=4.0,
                ),
            ),
            expected="Fingers move slowly",
        )

        session.step(
            instruction="Setting HIGH speed [100]*10 then opening fingers",
            action=lambda: (
                l20lite_hand.speed.set_speeds([100.0] * 10),
                move_and_wait(l20lite_hand, [100.0] * 10, wait_sec=2.0),
            ),
            expected="Fingers move fast",
        )

        session.step(
            instruction="Setting HIGH speed [100]*10 then closing fingers",
            action=lambda: (
                l20lite_hand.speed.set_speeds([100.0] * 10),
                move_and_wait(
                    l20lite_hand,
                    [0.0, 100.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 100],
                    wait_sec=2.0,
                ),
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
