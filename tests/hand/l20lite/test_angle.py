"""Tests for L20Lite AngleManager with hardware."""

import time

import pytest

from linkerbot import L20lite
from linkerbot.hand.l20lite import L20liteAngle
from tests.conftest import InteractiveSession
from tests.hand.l20lite.conftest import move_and_wait

pytestmark = [pytest.mark.l20lite, pytest.mark.control]

TOLERANCE = 15.0


class TestAngleManagerBlocking:
    """Test AngleManager blocking read."""

    def test_get_blocking_returns_valid_data(self, l20lite_hand: L20lite):
        """Blocking read should return 10 angles, all in [0, 100]."""
        data = l20lite_hand.angle.get_blocking(timeout_ms=500)

        assert data is not None
        assert len(data.angles) == 10
        for angle in data.angles.to_list():
            assert 0 <= angle <= 100, f"Angle {angle} out of range [0, 100]"

    def test_get_blocking_has_timestamp(self, l20lite_hand: L20lite):
        """Angle data timestamp should be positive and not in the future."""
        data = l20lite_hand.angle.get_blocking(timeout_ms=500)

        assert data.timestamp > 0
        assert data.timestamp <= time.time()


class TestAngleManagerSetAngles:
    """Test AngleManager set_angles method."""

    def test_set_angles_with_list(self, l20lite_hand: L20lite):
        """set_angles should accept list[float] without error and allow read-back."""
        target = [50.0, 100.0, 50.0, 50.0, 50.0, 50.0] + [100] * 4

        l20lite_hand.angle.set_angles(target)
        time.sleep(2.0)

        data = l20lite_hand.angle.get_blocking(timeout_ms=500)
        assert data is not None
        assert len(data.angles) == 10

    def test_set_angles_with_l20lite_angle(self, l20lite_hand: L20lite):
        """set_angles should accept L20liteAngle instance without error and allow read-back."""
        target = L20liteAngle(
            thumb_flex=50.0,
            thumb_abd=100.0,
            index_flex=50.0,
            middle_flex=50.0,
            ring_flex=50.0,
            pinky_flex=50.0,
            index_abd=100,
            ring_abd=100,
            pinky_abd=100,
            thumb_yaw=100,
        )

        l20lite_hand.angle.set_angles(target)
        time.sleep(2.0)

        data = l20lite_hand.angle.get_blocking(timeout_ms=500)
        assert data is not None
        assert len(data.angles) == 10

    def test_set_and_read_within_tolerance(self, l20lite_hand: L20lite):
        """Set [50]*10, read back, each angle should be within tolerance of target."""
        target = [
            50.0,
            100.0,
            50.0,
            50.0,
            50.0,
            50.0,
        ] + [100] * 4

        l20lite_hand.angle.set_angles(target)
        time.sleep(5)

        data = l20lite_hand.angle.get_blocking(timeout_ms=500)
        for i, expected in enumerate(target):
            assert abs(data.angles[i] - expected) < TOLERANCE, (
                f"Angle {i} expected ~{expected}, got {data.angles[i]}"
            )

    def test_set_all_closed(self, l20lite_hand: L20lite):
        """Set all-closed grip pose and verify read-back within tolerance.

        thumb_abd stays at 100 due to mechanical limit.
        """
        target = [18, 100.0, 0.0, 0.0, 0.0, 0.0] + [100] * 4

        l20lite_hand.angle.set_angles(target)
        time.sleep(5.0)

        data = l20lite_hand.angle.get_blocking(timeout_ms=500)
        for i, expected in enumerate(target):
            assert abs(data.angles[i] - expected) < TOLERANCE, (
                f"Angle {i} expected ~{expected}, got {data.angles[i]}"
            )

    def test_set_all_open(self, l20lite_hand: L20lite):
        """Set all-open pose [100]*10 and verify read-back within tolerance."""
        target = [100.0] * 10

        l20lite_hand.angle.set_angles(target)
        time.sleep(5.0)

        data = l20lite_hand.angle.get_blocking(timeout_ms=500)
        for i, expected in enumerate(target):
            assert abs(data.angles[i] - expected) < TOLERANCE, (
                f"Angle {i} expected ~{expected}, got {data.angles[i]}"
            )

    def test_set_individual_finger(self, l20lite_hand: L20lite):
        """Set one finger to a different value, verify it changed and others stayed."""
        # First move all to a known baseline
        baseline = [100.0] * 10
        l20lite_hand.angle.set_angles(baseline)
        time.sleep(5.0)

        l20lite_hand.angle.get_blocking(timeout_ms=500)

        # Change only the index_flex finger (index 2) to 0
        target = [100.0, 100.0, 0.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0]
        l20lite_hand.angle.set_angles(target)
        time.sleep(5.0)

        data = l20lite_hand.angle.get_blocking(timeout_ms=500)

        # The changed finger should be close to 0
        assert abs(data.angles[2] - 0.0) < TOLERANCE, (
            f"Index flex expected ~0, got {data.angles[2]}"
        )

        # Other fingers should remain roughly at baseline
        for i in [0, 1, 3, 4, 5, 6, 7, 8, 9]:
            assert abs(data.angles[i] - baseline[i]) < TOLERANCE, (
                f"Angle {i} expected ~{baseline[i]}, got {data.angles[i]}"
            )


class TestAngleManagerSnapshot:
    """Test AngleManager snapshot (cache) mode."""

    def test_snapshot_returns_none_before_any_read(self, l20lite_hand: L20lite):
        """On fresh connection, snapshot may be None or contain valid data."""
        data = l20lite_hand.angle.get_snapshot()
        assert data is None or hasattr(data, "angles")

    def test_snapshot_populated_after_blocking_read(self, l20lite_hand: L20lite):
        """After get_blocking(), get_snapshot() should return non-None with 10 angles."""
        l20lite_hand.angle.get_blocking(timeout_ms=500)

        data = l20lite_hand.angle.get_snapshot()
        assert data is not None
        assert len(data.angles) == 10


@pytest.mark.interactive
class TestAngleInteractive:
    """Interactive tests for angle control requiring human verification."""

    def test_full_open_and_close(
        self, l20lite_hand: L20lite, interactive_session: InteractiveSession
    ):
        """Human verifies hand opens fully then grips closed."""
        session = interactive_session

        session.step(
            instruction="Setting all fingers to fully open [100]*10",
            action=lambda: move_and_wait(l20lite_hand, [100.0] * 10, wait_sec=5.0),
            expected="All fingers should be fully open / extended",
        ).step(
            instruction="Setting all fingers to closed grip [0, 100, 0, 0, 0, 0, 0, 0, 0, 0]",
            action=lambda: move_and_wait(
                l20lite_hand,
                [0.0, 100.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                wait_sec=5.0,
            ),
            expected="All fingers should be gripped closed (thumb abduction stays open)",
        )

        session.run()
        session.save_report()

        if session.quit_early:
            pytest.exit("Tester quit early")

        failures = session.failed_steps()
        if failures:
            msgs = [f"- {f.instruction}: {f.notes}" for f in failures]
            pytest.fail(f"{len(failures)} step(s) failed:\n" + "\n".join(msgs))

    def test_individual_finger_movement(
        self, l20lite_hand: L20lite, interactive_session: InteractiveSession
    ):
        """Human verifies each finger moves independently."""
        session = interactive_session

        # Start from all-open position
        session.step(
            instruction="Setting all fingers to fully open [100]*10",
            action=lambda: move_and_wait(l20lite_hand, [100.0] * 10, wait_sec=5.0),
            expected="All fingers should be fully open / extended",
        )

        finger_names = [
            "thumb_flex",
            "thumb_abd",
            "index_flex",
            "middle_flex",
            "ring_flex",
            "pinky_flex",
            "index_abd",
            "ring_abd",
            "pinky_abd",
            "thumb_yaw",
        ]
        for finger_idx, finger_name in enumerate(finger_names):
            # Build target: all open (100), except the target finger set to 0,
            # and thumb_abd (index 1) always stays at 100
            target = [100.0] * 10
            if finger_name in ("thumb_abd", "thumb_yaw"):
                continue
            target[finger_idx] = 0.0
            target[1] = 100.0  # thumb_abd always 100
            target[9] = 100.0  # thumb_yaw always 100

            session.step(
                instruction=f"Bending {finger_name} to 0 (others open, thumb_abd and thumb_yaw=100)",
                action=lambda t=target: move_and_wait(l20lite_hand, t),
                expected=f"Only {finger_name} should be bent; all other fingers remain open",
            )

        session.run()
        session.save_report()

        if session.quit_early:
            pytest.exit("Tester quit early")

        failures = session.failed_steps()
        if failures:
            msgs = [f"- {f.instruction}: {f.notes}" for f in failures]
            pytest.fail(f"{len(failures)} step(s) failed:\n" + "\n".join(msgs))

    def test_gradual_movement(
        self, l20lite_hand: L20lite, interactive_session: InteractiveSession
    ):
        """Human verifies smooth gradual motion from 0 to 100."""
        session = interactive_session

        for pct in [0, 25, 50, 75, 100]:
            # All fingers go to pct, except thumb_abd stays at 100
            target = [float(pct)] * 10
            target[1] = 100.0  # thumb_abd always 100
            target[9] = 100.0  # thumb_yaw always 100
            session.step(
                instruction=f"Moving all fingers to {pct}% (thumb_abd and thumb_yaw=100)",
                action=lambda t=target: move_and_wait(l20lite_hand, t),
                expected=f"All fingers (except thumb abduction) should be at ~{pct}%",
            )

        session.run()
        session.save_report()

        if session.quit_early:
            pytest.exit("Tester quit early")

        failures = session.failed_steps()
        if failures:
            msgs = [f"- {f.instruction}: {f.notes}" for f in failures]
            pytest.fail(f"{len(failures)} step(s) failed:\n" + "\n".join(msgs))
