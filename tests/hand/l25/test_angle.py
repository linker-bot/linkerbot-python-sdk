"""Tests for L25 AngleManager with hardware."""

import threading
import time

import pytest

from linkerbot import L25
from linkerbot.hand.l25 import AngleEvent, L25Angle, SensorSource
from tests.conftest import InteractiveSession

pytestmark = [pytest.mark.l25, pytest.mark.control]

TOLERANCE = 5.0
MOTION_TIMEOUT_SEC = 5.0
_POLLING_INTERVAL_SEC = 0.4

# Hardware-verified poses
OPEN = [
    100.0,
    100.0,
    100.0,
    100.0,  # thumb: abd=100, yaw=100, root1=100, tip=100
    100.0,
    100.0,
    100.0,  # index: abd=100, root1=100, tip=100
    67.0,
    100.0,
    100.0,  # middle: abd=67, root1=100, tip=100
    33.0,
    100.0,
    100.0,  # ring: abd=33, root1=100, tip=100
    0.0,
    100.0,
    100.0,  # pinky: abd=0, root1=100, tip=100
]
CLOSED = [
    100.0,
    50.0,
    55.0,
    55.0,  # thumb: abd=100, yaw=50, root1=55, tip=55
    50.0,
    0.0,
    0.0,  # index: abd=50, root1=0, tip=0
    50.0,
    0.0,
    0.0,  # middle: abd=50, root1=0, tip=0
    50.0,
    0.0,
    0.0,  # ring: abd=50, root1=0, tip=0
    50.0,
    0.0,
    0.0,  # pinky: abd=50, root1=0, tip=0
]


def _move_until_settled(
    hand: L25,
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
            if all(abs(angles[i] - target[i]) < tolerance for i in range(16)):
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

    def test_get_blocking_returns_valid_data(self, l25_hand: L25):
        """Blocking read should return 16 angles, all in [0, 100]."""
        data = l25_hand.angle.get_blocking(timeout_ms=500)

        assert data is not None
        assert len(data.angles) == 16
        for angle in data.angles.to_list():
            assert 0 <= angle <= 100, f"Angle {angle} out of range [0, 100]"

        print(f"\n  Angles: {[f'{a:.1f}' for a in data.angles.to_list()]}")

    def test_get_blocking_has_timestamp(self, l25_hand: L25):
        """Angle data timestamp should be positive and not in the future."""
        data = l25_hand.angle.get_blocking(timeout_ms=500)

        assert data.timestamp > 0
        assert data.timestamp <= time.time()


class TestAngleManagerSetAngles:
    """Test AngleManager set_angles method."""

    def test_set_angles_with_list(self, l25_hand: L25):
        """set_angles should accept list[float] without error and allow read-back."""
        l25_hand.angle.set_angles(OPEN)
        time.sleep(2.0)

        data = l25_hand.angle.get_blocking(timeout_ms=500)
        assert data is not None
        assert len(data.angles) == 16
        print(
            f"\n  Read-back after set_angles (list): {[f'{a:.1f}' for a in data.angles.to_list()]}"
        )

    def test_set_angles_with_l25_angle(self, l25_hand: L25):
        """set_angles should accept L25Angle instance without error and allow read-back."""
        target = L25Angle(
            thumb_abd=100.0,
            thumb_yaw=100.0,
            thumb_root1=100.0,
            thumb_tip=100.0,
            index_abd=100.0,
            index_root1=100.0,
            index_tip=100.0,
            middle_abd=67.0,
            middle_root1=100.0,
            middle_tip=100.0,
            ring_abd=33.0,
            ring_root1=100.0,
            ring_tip=100.0,
            pinky_abd=0.0,
            pinky_root1=100.0,
            pinky_tip=100.0,
        )

        l25_hand.angle.set_angles(target)
        time.sleep(2.0)

        data = l25_hand.angle.get_blocking(timeout_ms=500)
        assert data is not None
        assert len(data.angles) == 16
        print(
            f"\n  Read-back after set_angles (L25Angle): {[f'{a:.1f}' for a in data.angles.to_list()]}"
        )

    def test_set_all_closed(self, l25_hand: L25):
        """Set closed grip pose and verify read-back within tolerance."""
        _move_until_settled(l25_hand, CLOSED, timeout_sec=10.0)

        data = l25_hand.angle.get_snapshot()
        assert data is not None
        for i, expected in enumerate(CLOSED):
            assert abs(data.angles[i] - expected) < TOLERANCE, (
                f"Angle {i} expected ~{expected}, got {data.angles[i]}"
            )

    def test_set_all_open(self, l25_hand: L25):
        """Set open pose and verify read-back within tolerance."""
        _move_until_settled(l25_hand, OPEN)

        data = l25_hand.angle.get_snapshot()
        assert data is not None
        for i, expected in enumerate(OPEN):
            assert abs(data.angles[i] - expected) < TOLERANCE, (
                f"Angle {i} expected ~{expected}, got {data.angles[i]}"
            )


class TestAngleManagerSnapshot:
    """Test AngleManager snapshot (cache) mode."""

    def test_snapshot_populated_after_blocking_read(self, l25_hand: L25):
        """After get_blocking(), get_snapshot() should return non-None with 16 angles."""
        l25_hand.angle.get_blocking(timeout_ms=500)

        data = l25_hand.angle.get_snapshot()
        assert data is not None
        assert len(data.angles) == 16

    def test_set_and_read_within_tolerance(self, l25_hand: L25):
        """Set open pose, read back, each angle within tolerance."""
        l25_hand.angle.set_angles(OPEN)
        time.sleep(4.0)

        data = l25_hand.angle.get_blocking(timeout_ms=500)
        for i, expected in enumerate(OPEN):
            assert abs(data.angles[i] - expected) < TOLERANCE, (
                f"Angle {i} expected ~{expected}, got {data.angles[i]}"
            )


@pytest.mark.interactive
class TestAngleInteractive:
    """Interactive tests for angle control requiring human verification."""

    def test_individual_finger_movement(
        self, l25_hand: L25, interactive_session: InteractiveSession
    ):
        """Human verifies each finger moves independently.

        Flow per joint: open → bend joint to 0 → confirm → open → next
        Skip thumb_abd (index 0) — always stays at 100.
        """
        session = interactive_session

        l25_hand.speed.set_speeds([100.0] * 16)

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

        session.step(
            instruction="Setting all joints to fully open pose",
            action=lambda: _move_until_settled(l25_hand, OPEN),
            expected="All fingers should be fully open / extended",
        )

        def _reset_then_bend(target: list[float]) -> None:
            _move_until_settled(l25_hand, OPEN)
            _move_until_settled(l25_hand, target)

        for joint_idx, joint_name in enumerate(joint_names):
            if joint_name == "thumb_abd":
                continue  # thumb_abd always stays at 100

            target = list(OPEN)
            target[joint_idx] = 0.0

            session.step(
                instruction=f"Bending {joint_name} (index {joint_idx}) to 0 (others open)",
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
        self, l25_hand: L25, interactive_session: InteractiveSession
    ):
        """Human verifies smooth gradual motion from open to closed."""
        session = interactive_session

        _move_until_settled(l25_hand, OPEN)

        for pct in [0, 25, 50, 75, 100]:
            # Build target: root1/tip joints go from OPEN(100) to CLOSED(0)
            # abd joints interpolate between CLOSED abd and OPEN abd
            # thumb_abd stays at 100 always
            open_arr = OPEN
            closed_arr = CLOSED
            target = [
                open_arr[i] + (closed_arr[i] - open_arr[i]) * pct / 100.0
                for i in range(16)
            ]
            target[0] = 100.0  # thumb_abd always 100

            session.step(
                instruction=f"Moving all fingers to {pct}% closed (thumb_abd=100)",
                action=lambda t=target: _move_until_settled(l25_hand, t),
                expected=f"All fingers (except thumb_abd) at ~{pct}% toward closed",
            )

        session.run()
        session.save_report()

        if session.quit_early:
            pytest.exit("Tester quit early")

        failures = session.failed_steps()
        if failures:
            msgs = [f"- {f.instruction}: {f.notes}" for f in failures]
            pytest.fail(f"{len(failures)} step(s) failed:\n" + "\n".join(msgs))
