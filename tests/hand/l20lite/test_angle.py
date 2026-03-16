"""Tests for L20Lite AngleManager with hardware."""

import threading
import time

import pytest

from linkerbot import L20lite
from linkerbot.hand.l20lite import AngleEvent, L20liteAngle, SensorSource
from tests.conftest import InteractiveSession

pytestmark = [pytest.mark.l20lite, pytest.mark.control]

TOLERANCE = 5.0
MOTION_TIMEOUT_SEC = 5.0
_POLLING_INTERVAL_SEC = 0.4


def _move_until_settled(
    hand: L20lite,
    target: list[float],
    tolerance: float = TOLERANCE,
    timeout_sec: float = MOTION_TIMEOUT_SEC,
) -> bool:
    """Set target angles, stream until within tolerance or timeout. Returns True if timed out."""
    hand.start_polling({SensorSource.ANGLE: _POLLING_INTERVAL_SEC})
    queue = hand.stream()
    hand.angle.set_angles(
        target
    )  # HACK: set_angles after stream() may race with polling
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
            if all(abs(angles[i] - target[i]) < tolerance for i in range(10)):
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

    def test_get_blocking_returns_valid_data(self, l20lite_hand: L20lite):
        """Blocking read should return 10 angles, all in [0, 100]."""
        data = l20lite_hand.angle.get_blocking(timeout_ms=500)

        assert data is not None
        assert len(data.angles) == 10
        for angle in data.angles.to_list():
            assert 0 <= angle <= 100, f"Angle {angle} out of range [0, 100]"

        print(f"\n  Angles: {[f'{a:.1f}' for a in data.angles.to_list()]}")

    def test_get_blocking_has_timestamp(self, l20lite_hand: L20lite):
        """Angle data timestamp should be positive and not in the future."""
        data = l20lite_hand.angle.get_blocking(timeout_ms=500)

        assert data.timestamp > 0
        assert data.timestamp <= time.time()


class TestAngleManagerSetAngles:
    """Test AngleManager set_angles method."""

    def test_set_angles_with_list(self, l20lite_hand: L20lite):
        """set_angles should accept list[float] without error and allow read-back."""
        target = [50.0, 100.0, 50.0, 50.0, 50.0, 50.0] + [100.0] * 4

        l20lite_hand.angle.set_angles(target)
        time.sleep(2.0)

        data = l20lite_hand.angle.get_blocking(timeout_ms=500)
        assert data is not None
        assert len(data.angles) == 10
        print(
            f"\n  Read-back after set_angles (list): {[f'{a:.1f}' for a in data.angles.to_list()]}"
        )

    def test_set_angles_with_l20lite_angle(self, l20lite_hand: L20lite):
        """set_angles should accept L20liteAngle instance without error and allow read-back."""
        target = L20liteAngle(
            thumb_flex=80.0,
            thumb_abd=80.0,
            index_flex=80.0,
            middle_flex=80.0,
            ring_flex=80.0,
            pinky_flex=80.0,
            index_abd=80.0,
            ring_abd=80.0,
            pinky_abd=80.0,
            thumb_yaw=80.0,
        )

        l20lite_hand.angle.set_angles(target)
        time.sleep(2.0)

        data = l20lite_hand.angle.get_blocking(timeout_ms=500)
        assert data is not None
        assert len(data.angles) == 10
        print(
            f"\n  Read-back after set_angles (L20liteAngle): {[f'{a:.1f}' for a in data.angles.to_list()]}"
        )

    def test_set_all_closed(self, l20lite_hand: L20lite):
        """Set all-closed grip pose and verify read-back within tolerance.

        thumb_abd stays at 100 due to mechanical limit.
        """
        target = [28.0, 100.0, 0.0, 0.0, 0.0, 0.0] + [100.0] * 4

        _move_until_settled(l20lite_hand, target)

        data = l20lite_hand.angle.get_snapshot()
        assert data is not None
        for i, expected in enumerate(target):
            assert abs(data.angles[i] - expected) < TOLERANCE, (
                f"Angle {i} expected ~{expected}, got {data.angles[i]}"
            )

    def test_set_all_open(self, l20lite_hand: L20lite):
        """Set all-open pose [100]*10 and verify read-back within tolerance."""
        target = [100.0] * 10

        _move_until_settled(l20lite_hand, target)

        data = l20lite_hand.angle.get_snapshot()
        assert data is not None
        for i, expected in enumerate(target):
            assert abs(data.angles[i] - expected) < TOLERANCE, (
                f"Angle {i} expected ~{expected}, got {data.angles[i]}"
            )


class TestAngleManagerSnapshot:
    """Test AngleManager snapshot (cache) mode."""

    def test_snapshot_populated_after_blocking_read(self, l20lite_hand: L20lite):
        """After get_blocking(), get_snapshot() should return non-None with 10 angles."""
        l20lite_hand.angle.get_blocking(timeout_ms=500)

        data = l20lite_hand.angle.get_snapshot()
        assert data is not None
        assert len(data.angles) == 10

    def test_set_and_read_within_tolerance(self, l20lite_hand: L20lite):
        """Set [50]*10 (with abd=100), read back, each angle within tolerance."""
        target = [50.0] * 10

        l20lite_hand.angle.set_angles(target)
        time.sleep(4.0)

        data = l20lite_hand.angle.get_blocking(timeout_ms=500)
        for i, expected in enumerate(target):
            assert abs(data.angles[i] - expected) < TOLERANCE, (
                f"Angle {i} expected ~{expected}, got {data.angles[i]}"
            )


@pytest.mark.interactive
class TestAngleInteractive:
    """Interactive tests for angle control requiring human verification."""

    def test_individual_finger_movement(
        self, l20lite_hand: L20lite, interactive_session: InteractiveSession
    ):
        """Human verifies each finger moves independently.

        Flow per joint: open [100]*10 → bend joint to 0 → confirm → open [100]*10 → next
        """
        session = interactive_session

        l20lite_hand.speed.set_speeds([100.0] * 10)

        joint_names = [
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

        session.step(
            instruction="Setting all joints to fully open [100]*10",
            action=lambda: _move_until_settled(l20lite_hand, [100.0] * 10),
            expected="All fingers should be fully open / extended",
        )

        def _reset_then_bend(target: list[float]) -> None:
            _move_until_settled(l20lite_hand, [100.0] * 10)
            _move_until_settled(l20lite_hand, target)

        for joint_idx, joint_name in enumerate(joint_names):
            target = [100.0] * 10
            target[joint_idx] = 0.0

            session.step(
                instruction=f"Bending {joint_name} (index {joint_idx}) to 0 (others 100)",
                action=lambda t=target: _reset_then_bend(t),
                expected=f"Only {joint_name} should be bent; all other joints remain open",
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

        _move_until_settled(l20lite_hand, [100.0] * 10)

        for pct in [0, 25, 50, 75, 100]:
            target = [float(pct)] * 10
            if pct == 0:
                target[0] = 20.0  # prevent thumb from catching bent index
            target[1] = 100.0  # thumb_abd always 100
            target[9] = 100.0  # thumb_yaw always 100

            session.step(
                instruction=f"Moving all fingers to {pct}% (thumb_abd and thumb_yaw=100)",
                action=lambda t=target: _move_until_settled(l20lite_hand, t),
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
