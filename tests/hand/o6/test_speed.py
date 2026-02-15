"""Tests for O6 SpeedManager with hardware."""

import time

import pytest

from linkerbot import O6
from linkerbot.hand.o6 import O6Speed
from tests.conftest import InteractiveSession
from tests.hand.o6.conftest import move_and_wait

pytestmark = [pytest.mark.o6, pytest.mark.control]


class TestSpeedManagerBlocking:
    """Test SpeedManager blocking read."""

    def test_get_blocking_returns_valid_data(self, o6_hand: O6):
        """Blocking read should return 6 speeds, all in [0, 100]."""
        data = o6_hand.speed.get_blocking(timeout_ms=500)

        assert data is not None
        assert len(data.speeds) == 6
        for speed in data.speeds.to_list():
            assert 0 <= speed <= 100, f"Speed {speed} out of range [0, 100]"

    def test_get_blocking_has_timestamp(self, o6_hand: O6):
        """Speed data timestamp should be positive and not in the future."""
        data = o6_hand.speed.get_blocking(timeout_ms=500)

        assert data.timestamp > 0
        assert data.timestamp <= time.time()


class TestSpeedManagerSet:
    """Test SpeedManager set_speeds method."""

    def test_set_speeds_with_list(self, o6_hand: O6):
        """set_speeds should accept a list of floats without error."""
        o6_hand.speed.set_speeds([50.0] * 6)

    def test_set_speeds_with_o6speed(self, o6_hand: O6):
        """set_speeds should accept an O6Speed instance without error."""
        o6_hand.speed.set_speeds(
            O6Speed(
                thumb_flex=50.0,
                thumb_abd=50.0,
                index=50.0,
                middle=50.0,
                ring=50.0,
                pinky=50.0,
            )
        )

    def test_set_different_speeds(self, o6_hand: O6):
        """set_speeds should accept different per-motor speeds without error."""
        o6_hand.speed.set_speeds([20.0, 40.0, 60.0, 80.0, 100.0, 50.0])


class TestSpeedManagerSnapshot:
    """Test SpeedManager snapshot (cache) mode."""

    def test_snapshot_populated_after_blocking_read(self, o6_hand: O6):
        """get_snapshot should return data after a blocking read."""
        o6_hand.speed.get_blocking(timeout_ms=500)

        data = o6_hand.speed.get_snapshot()

        assert data is not None
        assert len(data.speeds) == 6


@pytest.mark.interactive
class TestSpeedInteractive:
    """Interactive tests for verifying speed affects movement."""

    def test_speed_affects_movement(
        self, o6_hand: O6, interactive_session: InteractiveSession
    ):
        """Verify that speed settings visibly affect finger movement speed."""
        session = interactive_session

        session.step(
            instruction="Setting LOW speed [10]*6 then closing fingers",
            action=lambda: (
                o6_hand.speed.set_speeds([10.0] * 6),
                move_and_wait(o6_hand, [0.0, 100.0, 0.0, 0.0, 0.0, 0.0], wait_sec=4.0),
            ),
            expected="Fingers move slowly",
        )

        session.step(
            instruction="Setting HIGH speed [100]*6 then opening fingers",
            action=lambda: (
                o6_hand.speed.set_speeds([100.0] * 6),
                move_and_wait(o6_hand, [100.0] * 6, wait_sec=2.0),
            ),
            expected="Fingers move fast",
        )

        session.step(
            instruction="Setting HIGH speed [100]*6 then closing fingers",
            action=lambda: (
                o6_hand.speed.set_speeds([100.0] * 6),
                move_and_wait(o6_hand, [0.0, 100.0, 0.0, 0.0, 0.0, 0.0], wait_sec=2.0),
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
