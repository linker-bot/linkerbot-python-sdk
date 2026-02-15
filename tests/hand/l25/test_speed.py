"""Tests for L25 SpeedManager with hardware."""

import pytest

from linkerbot import L25
from linkerbot.hand.l25 import L25Speed
from tests.conftest import InteractiveSession
from tests.hand.l25.conftest import move_and_wait

pytestmark = [pytest.mark.l25, pytest.mark.control]


class TestSpeedManagerSet:
    """Test SpeedManager set_speeds method."""

    def test_set_speeds_with_list(self, l25_hand: L25):
        """set_speeds should accept a list of floats without error."""
        l25_hand.speed.set_speeds([50.0] * 16)

    def test_set_speeds_with_l25_speed(self, l25_hand: L25):
        """set_speeds should accept an L25Speed instance without error."""
        l25_hand.speed.set_speeds(
            L25Speed(
                thumb_abd=100.0,
                thumb_yaw=100.0,
                thumb_root1=50.0,
                thumb_tip=50.0,
                index_abd=50.0,
                index_root1=50.0,
                index_tip=50.0,
                middle_abd=50.0,
                middle_root1=50.0,
                middle_tip=50.0,
                ring_abd=50.0,
                ring_root1=50.0,
                ring_tip=50.0,
                pinky_abd=50.0,
                pinky_root1=50.0,
                pinky_tip=50.0,
            )
        )

    def test_set_different_speeds(self, l25_hand: L25):
        """set_speeds should accept different per-motor speeds without error."""
        l25_hand.speed.set_speeds(
            [
                20.0,
                40.0,
                60.0,
                80.0,
                100.0,
                50.0,
                30.0,
                70.0,
                90.0,
                10.0,
                25.0,
                45.0,
                65.0,
                85.0,
                55.0,
                35.0,
            ]
        )


class TestSpeedManagerBlocking:
    """Test SpeedManager blocking read."""

    def test_get_blocking_returns_valid_data(self, l25_hand: L25):
        """Blocking read should return 16 speed values."""
        data = l25_hand.speed.get_blocking(timeout_ms=500)

        assert data is not None
        assert len(data.speeds) == 16

    def test_get_blocking_has_timestamp(self, l25_hand: L25):
        """Speed data should have a valid timestamp."""
        data = l25_hand.speed.get_blocking(timeout_ms=500)

        assert data.timestamp > 0


@pytest.mark.interactive
class TestSpeedInteractive:
    """Interactive tests for verifying speed affects movement."""

    def test_speed_affects_movement(
        self, l25_hand: L25, interactive_session: InteractiveSession
    ):
        """Verify that speed settings visibly affect finger movement speed."""
        session = interactive_session

        session.step(
            instruction="Setting LOW speed [10]*16 then closing fingers",
            action=lambda: (
                l25_hand.speed.set_speeds([10.0] * 16),
                move_and_wait(
                    l25_hand,
                    [
                        100.0,
                        100.0,
                        20.0,
                        0.0,
                        0.0,
                        20.0,
                        0.0,
                        0.0,
                        20.0,
                        0.0,
                        0.0,
                        20.0,
                        0.0,
                        0.0,
                        20.0,
                        0.0,
                    ],
                    wait_sec=4.0,
                ),
            ),
            expected="Fingers move slowly",
        )

        session.step(
            instruction="Setting HIGH speed [100]*16 then opening fingers",
            action=lambda: (
                l25_hand.speed.set_speeds([100.0] * 16),
                move_and_wait(l25_hand, [100.0] * 16, wait_sec=2.0),
            ),
            expected="Fingers move fast",
        )

        session.step(
            instruction="Setting HIGH speed [100]*16 then closing fingers",
            action=lambda: (
                l25_hand.speed.set_speeds([100.0] * 16),
                move_and_wait(
                    l25_hand,
                    [
                        100.0,
                        100.0,
                        20.0,
                        0.0,
                        0.0,
                        20.0,
                        0.0,
                        0.0,
                        20.0,
                        0.0,
                        0.0,
                        20.0,
                        0.0,
                        0.0,
                        20.0,
                        0.0,
                    ],
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
