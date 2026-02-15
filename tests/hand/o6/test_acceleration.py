"""Tests for O6 AccelerationManager with hardware."""

import time

import pytest

from linkerbot import O6
from linkerbot.hand.o6 import O6Acceleration
from tests.conftest import InteractiveSession
from tests.hand.o6.conftest import move_and_wait

pytestmark = [pytest.mark.o6, pytest.mark.control]


class TestAccelerationManagerBlocking:
    """Test AccelerationManager blocking read."""

    def test_get_blocking_returns_valid_data(self, o6_hand: O6):
        """Blocking read should return 6 acceleration values, all in [0, 100]."""
        data = o6_hand.acceleration.get_blocking(timeout_ms=500)

        assert data is not None
        assert len(data.accelerations) == 6
        for accel in data.accelerations.to_list():
            assert 0 <= accel <= 100, f"Acceleration {accel} out of range [0, 100]"

    def test_get_blocking_has_timestamp(self, o6_hand: O6):
        """Acceleration data timestamp should be positive and not in the future."""
        data = o6_hand.acceleration.get_blocking(timeout_ms=500)

        assert data.timestamp > 0
        assert data.timestamp <= time.time()


class TestAccelerationManagerSet:
    """Test AccelerationManager set_accelerations method."""

    def test_set_accelerations_with_list(self, o6_hand: O6):
        """set_accelerations should accept a list of floats without error."""
        o6_hand.acceleration.set_accelerations([50.0] * 6)

    def test_set_accelerations_with_o6acceleration(self, o6_hand: O6):
        """set_accelerations should accept an O6Acceleration instance without error."""
        o6_hand.acceleration.set_accelerations(
            O6Acceleration(
                thumb_flex=50.0,
                thumb_abd=50.0,
                index=50.0,
                middle=50.0,
                ring=50.0,
                pinky=50.0,
            )
        )

    def test_set_different_accelerations(self, o6_hand: O6):
        """set_accelerations should accept different per-motor values without error."""
        o6_hand.acceleration.set_accelerations([20.0, 40.0, 60.0, 80.0, 100.0, 50.0])


class TestAccelerationManagerSnapshot:
    """Test AccelerationManager snapshot (cache) mode."""

    def test_snapshot_populated_after_blocking_read(self, o6_hand: O6):
        """get_snapshot should return data after a blocking read."""
        o6_hand.acceleration.get_blocking(timeout_ms=500)

        data = o6_hand.acceleration.get_snapshot()

        assert data is not None
        assert len(data.accelerations) == 6


@pytest.mark.interactive
class TestAccelerationInteractive:
    """Interactive tests for verifying acceleration affects movement ramp-up."""

    def test_acceleration_affects_movement(
        self, o6_hand: O6, interactive_session: InteractiveSession
    ):
        """Verify that acceleration settings visibly affect finger movement ramp-up."""
        session = interactive_session

        session.step(
            instruction="Setting LOW acceleration [10]*6 then closing fingers",
            action=lambda: (
                o6_hand.acceleration.set_accelerations([10.0] * 6),
                move_and_wait(o6_hand, [0.0, 100.0, 0.0, 0.0, 0.0, 0.0], wait_sec=4.0),
            ),
            expected="Fingers ramp up slowly, gradual start to movement",
        )

        session.step(
            instruction="Setting HIGH acceleration [100]*6 then opening fingers",
            action=lambda: (
                o6_hand.acceleration.set_accelerations([100.0] * 6),
                move_and_wait(o6_hand, [100.0] * 6, wait_sec=2.0),
            ),
            expected="Fingers start moving immediately with sharp acceleration",
        )

        session.step(
            instruction="Setting HIGH acceleration [100]*6 then closing fingers",
            action=lambda: (
                o6_hand.acceleration.set_accelerations([100.0] * 6),
                move_and_wait(o6_hand, [0.0, 100.0, 0.0, 0.0, 0.0, 0.0], wait_sec=2.0),
            ),
            expected="Clearly faster ramp-up than the first step",
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
