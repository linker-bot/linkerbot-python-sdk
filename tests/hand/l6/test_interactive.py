"""Interactive tests for L6 robotic hand requiring human observation."""

import time

import pytest

from linkerbot import L6
from tests.conftest import InteractiveSession

pytestmark = [pytest.mark.interactive, pytest.mark.l6]


def move_and_wait(hand: L6, angles: list[float], wait_sec: float = 1.0):
    """Helper to move hand and wait for completion."""
    hand.angle.set_angles(angles)
    time.sleep(wait_sec)


class TestMovementVerification:
    """Verify that angle commands produce correct physical movements."""

    def test_all_finger_range(
        self, l6_hand: L6, interactive_session: InteractiveSession
    ):
        """Verify thumb moves through full range of motion."""
        session = interactive_session

        session.step(
            instruction="Moving all fingers to fully open position (100%)",
            action=lambda: move_and_wait(l6_hand, [100.0] * 6),
            expected="Fingers should be fully extended",
        ).step(
            instruction="Moving all fingers to mid position (50%)",
            action=lambda: move_and_wait(
                l6_hand, [50.0, 100.0, 50.0, 50.0, 50.0, 50.0]
            ),
            expected="Fingers should be at mid-range",
        )

        session.run()
        session.save_report()

        if session.failed_steps():
            pytest.fail(
                f"Interactive test failed: {len(session.failed_steps())} step(s) did not pass"
            )


class TestForceSensorVerification:
    """Verify force sensor readings respond to physical pressure."""

    def test_force_sensor_responds_to_pressure(
        self, l6_hand: L6, interactive_session: InteractiveSession
    ):
        """Verify force sensors detect pressure changes."""
        session = interactive_session

        # Store readings for comparison
        readings: dict[str, str] = {}

        def read_initial():
            data = l6_hand.force_sensor.get_data_blocking(timeout_ms=1000)
            readings["initial"] = str(data.thumb.values)
            print(f"Initial thumb reading: {readings['initial']}")

        def read_after_pressure():
            data = l6_hand.force_sensor.get_data_blocking(timeout_ms=1000)
            readings["after"] = str(data.thumb.values)
            print(f"After pressure thumb reading: {readings['after']}")

        session.step(
            instruction="Reading initial force sensor value (no pressure)",
            action=read_initial,
            expected="Baseline reading displayed",
        ).step(
            instruction="Apply pressure to thumb fingertip, then reading sensor",
            action=read_after_pressure,
            expected="Force sensor values should be higher than baseline",
        )

        session.run()
        session.save_report()

        if session.failed_steps():
            pytest.fail(
                f"Interactive test failed: {len(session.failed_steps())} step(s) did not pass"
            )
