"""Tests for L25 AngleManager with hardware."""

import time

import pytest

from linkerbot import L25
from linkerbot.hand.l25 import L25Angle
from tests.conftest import InteractiveSession
from tests.hand.l25.conftest import move_and_wait

pytestmark = [pytest.mark.l25, pytest.mark.control]

TOLERANCE = 15.0


class TestAngleManagerBlocking:
    """Test AngleManager blocking read."""

    def test_get_blocking_returns_valid_data(self, l25_hand: L25):
        """Blocking read should return 16 angles, all in [0, 100]."""
        data = l25_hand.angle.get_blocking(timeout_ms=500)

        assert data is not None
        assert len(data.angles) == 16
        for angle in data.angles.to_list():
            assert 0 <= angle <= 100, f"Angle {angle} out of range [0, 100]"

    def test_get_blocking_has_timestamp(self, l25_hand: L25):
        """Angle data timestamp should be positive and not in the future."""
        data = l25_hand.angle.get_blocking(timeout_ms=500)

        assert data.timestamp > 0
        assert data.timestamp <= time.time()


class TestAngleManagerSetAngles:
    """Test AngleManager set_angles method."""

    def test_set_angles_with_list(self, l25_hand: L25):
        """set_angles should accept list[float] without error and allow read-back."""
        target = [
            100.0,
            100.0,
            50.0,
            50.0,
            50.0,
            50.0,
            50.0,
            50.0,
            50.0,
            50.0,
            50.0,
            50.0,
            50.0,
            50.0,
            50.0,
            50.0,
        ]

        l25_hand.angle.set_angles(target)
        time.sleep(2.0)

        data = l25_hand.angle.get_blocking(timeout_ms=500)
        assert data is not None
        assert len(data.angles) == 16

    def test_set_angles_with_l25_angle(self, l25_hand: L25):
        """set_angles should accept L25Angle instance without error and allow read-back."""
        target = L25Angle(
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

        l25_hand.angle.set_angles(target)
        time.sleep(2.0)

        data = l25_hand.angle.get_blocking(timeout_ms=500)
        assert data is not None
        assert len(data.angles) == 16

    def test_set_and_read_within_tolerance(self, l25_hand: L25):
        """Set target angles, read back, each angle should be within tolerance."""
        target = [100.0, 100.0] + [50.0] * 14

        l25_hand.angle.set_angles(target)
        time.sleep(5)

        data = l25_hand.angle.get_blocking(timeout_ms=500)
        for i, expected in enumerate(target):
            assert abs(data.angles[i] - expected) < TOLERANCE, (
                f"Angle {i} expected ~{expected}, got {data.angles[i]}"
            )

    def test_set_all_closed(self, l25_hand: L25):
        """Set all-closed grip pose and verify read-back within tolerance.

        thumb_abd and thumb_yaw stay at 100 due to mechanical constraint.
        """
        target: list[float] = [
            100.0,
            100.0,
            100.0,
            100.0,
            100.0,
            100,
            0.0,
            100,
            20.0,
            0.0,
            0.0,
            20.0,
            0.0,
            0.0,
            20.0,
            0.0,
        ]

        l25_hand.angle.set_angles(target)
        time.sleep(7.0)

        data = l25_hand.angle.get_blocking(timeout_ms=500)
        for i, expected in enumerate(target):
            assert abs(data.angles[i] - expected) < TOLERANCE, (
                f"Angle {i} expected ~{expected}, got {data.angles[i]}"
            )

    def test_set_all_open(self, l25_hand: L25):
        """Set all-open pose [100]*16 and verify read-back within tolerance."""
        target = [100.0] * 16

        l25_hand.angle.set_angles(target)
        time.sleep(5.0)

        data = l25_hand.angle.get_blocking(timeout_ms=500)
        for i, expected in enumerate(target):
            assert abs(data.angles[i] - expected) < TOLERANCE, (
                f"Angle {i} expected ~{expected}, got {data.angles[i]}"
            )

    def test_set_individual_finger(self, l25_hand: L25):
        """Set one finger to a different value, verify it changed and others stayed."""
        baseline = [100.0] * 16
        l25_hand.angle.set_angles(baseline)
        time.sleep(5.0)

        l25_hand.angle.get_blocking(timeout_ms=500)

        # Change only index_root1 (index 5) to 20 (root1 minimum)
        target = [100.0] * 16
        target[5] = 20.0
        l25_hand.angle.set_angles(target)
        time.sleep(5.0)

        data = l25_hand.angle.get_blocking(timeout_ms=500)

        # The changed finger should be close to 20
        assert abs(data.angles[5] - 20.0) < TOLERANCE, (
            f"index_root1 expected ~20, got {data.angles[5]}"
        )

        # Other fingers should remain roughly at baseline
        for i in range(16):
            if i == 5:
                continue
            assert abs(data.angles[i] - baseline[i]) < TOLERANCE, (
                f"Angle {i} expected ~{baseline[i]}, got {data.angles[i]}"
            )


class TestAngleManagerSnapshot:
    """Test AngleManager snapshot (cache) mode."""

    def test_snapshot_returns_none_before_any_read(self, l25_hand: L25):
        """On fresh connection, snapshot may be None or contain valid data."""
        data = l25_hand.angle.get_snapshot()
        assert data is None or hasattr(data, "angles")

    def test_snapshot_populated_after_blocking_read(self, l25_hand: L25):
        """After get_blocking(), get_snapshot() should return non-None with 16 angles."""
        l25_hand.angle.get_blocking(timeout_ms=500)

        data = l25_hand.angle.get_snapshot()
        assert data is not None
        assert len(data.angles) == 16


@pytest.mark.interactive
class TestAngleInteractive:
    """Interactive tests for angle control requiring human verification."""

    def test_full_open_and_close(
        self, l25_hand: L25, interactive_session: InteractiveSession
    ):
        """Human verifies hand opens fully then grips closed."""
        session = interactive_session

        session.step(
            instruction="Setting all fingers to fully open [100]*16",
            action=lambda: move_and_wait(l25_hand, [100.0] * 16, wait_sec=5.0),
            expected="All fingers should be fully open / extended",
        ).step(
            instruction="Setting all fingers to closed grip",
            action=lambda: move_and_wait(
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
                wait_sec=5.0,
            ),
            expected="All fingers should be gripped closed (thumb_abd and thumb_yaw stay open)",
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
        self, l25_hand: L25, interactive_session: InteractiveSession
    ):
        """Human verifies each finger moves independently."""
        session = interactive_session

        # Start from all-open position
        session.step(
            instruction="Setting all fingers to fully open [100]*16",
            action=lambda: move_and_wait(l25_hand, [100.0] * 16, wait_sec=5.0),
            expected="All fingers should be fully open / extended",
        )

        joint_names = [
            "thumb_abd",
            "thumb_yaw",
            "thumb_root1",
            "thumb_tip",
            "index_abd",
            "index_root1",
            "index_tip",
            "middle_abd",
            "middle_root1",
            "middle_tip",
            "ring_abd",
            "ring_root1",
            "ring_tip",
            "pinky_abd",
            "pinky_root1",
            "pinky_tip",
        ]
        for joint_idx, joint_name in enumerate(joint_names):
            # Skip thumb_abd (idx 0) and thumb_yaw (idx 1) — always 100
            if joint_name in ("thumb_abd", "thumb_yaw"):
                continue
            target = [100.0] * 16
            target[joint_idx] = 0.0
            target[0] = 100.0  # thumb_abd always 100
            target[1] = 100.0  # thumb_yaw always 100

            session.step(
                instruction=f"Bending {joint_name} to 0 (others open, thumb_abd and thumb_yaw=100)",
                action=lambda t=target: move_and_wait(l25_hand, t),
                expected=f"Only {joint_name} should be bent; all other fingers remain open",
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
        self, l25_hand: L25, interactive_session: InteractiveSession
    ):
        """Human verifies smooth gradual motion from 0 to 100."""
        session = interactive_session

        for pct in [0, 25, 50, 75, 100]:
            # All fingers go to pct, except thumb_abd and thumb_yaw stay at 100
            # root1 joints (indices 2,5,8,11,14) have minimum of 20
            target = [float(pct)] * 16
            target[0] = 100.0  # thumb_abd always 100
            target[1] = 100.0  # thumb_yaw always 100
            for ri in (2, 5, 8, 11, 14):
                target[ri] = max(float(pct), 20.0)
            session.step(
                instruction=f"Moving all fingers to {pct}% (thumb_abd and thumb_yaw=100)",
                action=lambda t=target: move_and_wait(l25_hand, t),
                expected=f"All fingers (except thumb_abd and thumb_yaw) should be at ~{pct}%",
            )

        session.run()
        session.save_report()

        if session.quit_early:
            pytest.exit("Tester quit early")

        failures = session.failed_steps()
        if failures:
            msgs = [f"- {f.instruction}: {f.notes}" for f in failures]
            pytest.fail(f"{len(failures)} step(s) failed:\n" + "\n".join(msgs))
