"""Tests for L6 AngleManager with hardware."""

import threading
import time

import pytest

from linkerbot import L6
from linkerbot.hand.l6 import AngleEvent, L6Angle, SensorSource
from tests.conftest import InteractiveSession

pytestmark = [pytest.mark.l6, pytest.mark.control]

TOLERANCE = 15.0
MOTION_TIMEOUT_SEC = 5.0
_POLLING_INTERVAL_SEC = 0.1


def _move_until_settled(
    hand: L6,
    target: list[float],
    tolerance: float = TOLERANCE,
    timeout_sec: float = MOTION_TIMEOUT_SEC,
) -> bool:
    """Set target angles, stream until within tolerance or timeout. Returns True if timed out."""
    hand.start_polling({SensorSource.ANGLE: _POLLING_INTERVAL_SEC})
    queue = hand.stream()
    hand.angle.set_angles(target)
    start = time.perf_counter()
    deadline = start + timeout_sec
    timed_out = False
    timer = threading.Timer(timeout_sec, hand.stop_stream)
    timer.start()
    try:
        for event in queue:
            if not isinstance(event, AngleEvent):
                continue
            angles = event.data.angles
            if all(abs(angles[i] - target[i]) < tolerance for i in range(6)):
                break
            if time.perf_counter() >= deadline:
                timed_out = True
                break
    finally:
        timer.cancel()
        hand.stop_stream()
        hand.stop_polling()
    elapsed = time.perf_counter() - start
    data = hand.angle.get_snapshot()
    print(
        f"\n  Motion time: {elapsed:.2f}s | "
        f"Angles: {[f'{a:.1f}' for a in data.angles.to_list()] if data else 'N/A'}"
    )
    return timed_out


class TestAngleManagerBlocking:
    """Test AngleManager blocking read."""

    def test_get_blocking_returns_valid_data(self, l6_hand: L6):
        """Blocking read should return 6 angles, all in [0, 100]."""
        data = l6_hand.angle.get_blocking(timeout_ms=500)

        assert data is not None
        assert len(data.angles) == 6
        for angle in data.angles.to_list():
            assert 0 <= angle <= 100, f"Angle {angle} out of range [0, 100]"

        print(f"\n  Angles: {[f'{a:.1f}' for a in data.angles.to_list()]}")

    def test_get_blocking_has_timestamp(self, l6_hand: L6):
        """Angle data timestamp should be positive and not in the future."""
        data = l6_hand.angle.get_blocking(timeout_ms=500)

        assert data.timestamp > 0
        assert data.timestamp <= time.time()


class TestAngleManagerSetAngles:
    """Test AngleManager set_angles method."""

    def test_set_angles_with_list(self, l6_hand: L6):
        """set_angles should accept list[float] without error and allow read-back."""
        target = [50.0, 100.0, 50.0, 50.0, 50.0, 50.0]

        l6_hand.angle.set_angles(target)
        time.sleep(2.0)

        data = l6_hand.angle.get_blocking(timeout_ms=500)
        assert data is not None
        assert len(data.angles) == 6
        print(
            f"\n  Read-back after set_angles (list): {[f'{a:.1f}' for a in data.angles.to_list()]}"
        )

    def test_set_angles_with_l6angle(self, l6_hand: L6):
        """set_angles should accept L6Angle instance without error and allow read-back."""
        target = L6Angle(
            thumb_flex=50.0,
            thumb_abd=100.0,
            index=50.0,
            middle=50.0,
            ring=50.0,
            pinky=50.0,
        )

        l6_hand.angle.set_angles(target)
        time.sleep(2.0)

        data = l6_hand.angle.get_blocking(timeout_ms=500)
        assert data is not None
        assert len(data.angles) == 6
        print(
            f"\n  Read-back after set_angles (L6Angle): {[f'{a:.1f}' for a in data.angles.to_list()]}"
        )

    def test_set_all_closed(self, l6_hand: L6):
        """Set all-closed grip pose and verify read-back within tolerance.

        thumb_abd stays at 100 due to mechanical limit.
        """
        target = [0.0, 100.0, 0.0, 0.0, 0.0, 0.0]

        _move_until_settled(l6_hand, target)

        data = l6_hand.angle.get_snapshot()
        assert data is not None
        for i, expected in enumerate(target):
            assert abs(data.angles[i] - expected) < TOLERANCE, (
                f"Angle {i} expected ~{expected}, got {data.angles[i]}"
            )

    def test_set_all_open(self, l6_hand: L6):
        """Set all-open pose [100]*6 and verify read-back within tolerance."""
        target = [100.0] * 6

        _move_until_settled(l6_hand, target)

        data = l6_hand.angle.get_snapshot()
        assert data is not None
        for i, expected in enumerate(target):
            assert abs(data.angles[i] - expected) < TOLERANCE, (
                f"Angle {i} expected ~{expected}, got {data.angles[i]}"
            )


class TestAngleManagerSnapshot:
    """Test AngleManager snapshot (cache) mode."""

    def test_snapshot_populated_after_blocking_read(self, l6_hand: L6):
        """After get_blocking(), get_snapshot() should return non-None with 6 angles."""
        l6_hand.angle.get_blocking(timeout_ms=500)

        data = l6_hand.angle.get_snapshot()
        assert data is not None
        assert len(data.angles) == 6

    def test_set_and_read_within_tolerance(self, l6_hand: L6):
        """Set [50]*6, read back, each angle should be within tolerance of target."""
        target = [50.0] * 6

        l6_hand.angle.set_angles(target)
        time.sleep(4.0)

        data = l6_hand.angle.get_blocking(timeout_ms=500)
        for i, expected in enumerate(target):
            assert abs(data.angles[i] - expected) < TOLERANCE, (
                f"Angle {i} expected ~{expected}, got {data.angles[i]}"
            )


@pytest.mark.interactive
class TestAngleInteractive:
    """Interactive tests for angle control requiring human verification."""

    def test_individual_finger_movement(
        self, l6_hand: L6, interactive_session: InteractiveSession
    ):
        """Human verifies each finger moves independently."""
        session = interactive_session

        def _reset_then_bend(target: list[float]) -> None:
            _move_until_settled(l6_hand, [100.0] * 6)
            _move_until_settled(l6_hand, target)

        session.step(
            instruction="Setting all fingers to fully open [100]*6",
            action=lambda: _move_until_settled(l6_hand, [100.0] * 6),
            expected="All fingers should be fully open / extended",
        )

        finger_names = ["thumb_flex", "thumb_abd", "index", "middle", "ring", "pinky"]
        for finger_idx, finger_name in enumerate(finger_names):
            target = [100.0] * 6
            target[finger_idx] = 0.0
            if finger_idx != 1:
                target[1] = 100.0  # thumb_abd stays at 100 except when testing it

            session.step(
                instruction=f"Bending {finger_name} (index {finger_idx}) to 0 (others 100)",
                action=lambda t=target: _reset_then_bend(t),
                expected=f"Only {finger_name} should be bent; all other joints remain open",
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
        self, l6_hand: L6, interactive_session: InteractiveSession
    ):
        """Human verifies smooth gradual motion from 0 to 100."""
        session = interactive_session

        _move_until_settled(l6_hand, [100.0] * 6)

        for pct in [0, 25, 50, 75, 100]:
            target = [float(pct)] * 6
            target[1] = 100.0  # thumb_abd always 100

            session.step(
                instruction=f"Moving all fingers to {pct}% (thumb_abd=100)",
                action=lambda t=target: _move_until_settled(l6_hand, t),
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
