"""Tests for O6 SpeedManager with hardware."""

import threading
import time

import pytest

from linkerbot import O6
from linkerbot.hand.o6 import AngleEvent, O6Speed, SensorSource
from tests.conftest import InteractiveSession

pytestmark = [pytest.mark.o6, pytest.mark.control]

TOLERANCE = 3.0
MOTION_TIMEOUT_SEC = 10.0
_POLLING_INTERVAL_SEC = 0.1

OPEN = [100.0] * 6
CLOSED = [0.0, 100.0, 0.0, 0.0, 0.0, 0.0]


def _move_and_time(
    hand: O6,
    target: list[float],
    tolerance: float = TOLERANCE,
    timeout_sec: float = MOTION_TIMEOUT_SEC,
) -> tuple[float, bool]:
    """Set target angles, stream until within tolerance, return (elapsed_seconds, timed_out)."""
    timed_out = False
    hand.start_polling({SensorSource.ANGLE: _POLLING_INTERVAL_SEC})
    queue = hand.stream()
    hand.angle.set_angles(target)
    start = time.perf_counter()
    deadline = start + timeout_sec
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
                print(f"\n  [TIMEOUT] Did not reach target within {timeout_sec:.0f}s")
                timed_out = True
                break
    finally:
        timer.cancel()
        hand.stop_stream()
        hand.stop_polling()

    elapsed = time.perf_counter() - start
    data = hand.angle.get_blocking(timeout_ms=500)
    print(
        f"\n  Motion time: {elapsed:.2f}s | "
        f"Angles: {[f'{a:.1f}' for a in data.angles.to_list()]}"
    )
    return elapsed, timed_out


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
        motion_results: list[tuple[str, float, bool]] = []

        def track(label: str, target: list[float]) -> None:
            elapsed, timed_out = _move_and_time(o6_hand, target)
            motion_results.append((label, elapsed, timed_out))

        for level, speed_val in [("LOW", 10.0), ("MID", 30.0), ("HIGH", 100.0)]:
            session.step(
                instruction=f"[{level} speed={speed_val}] Closing fingers",
                action=lambda lbl=f"{level} close", sv=speed_val: (
                    o6_hand.speed.set_speeds([sv] * 6),
                    track(lbl, CLOSED),
                ),
                expected=(
                    f"Fingers close at {level} speed "
                    f"({'slow' if level == 'LOW' else 'medium' if level == 'MID' else 'fast'})"
                ),
            )

            session.step(
                instruction=f"[{level} speed={speed_val}] Opening hand",
                action=lambda lbl=f"{level} open": (track(lbl, OPEN),),
                expected="Fingers fully open",
            )

        session.run()

        _move_and_time(o6_hand, OPEN)

        print("\n" + "=" * 52)
        print("  Motion Time Summary")
        print("=" * 52)
        for label, elapsed, timed_out in motion_results:
            timeout_mark = "  [TIMEOUT]" if timed_out else ""
            print(f"  {label:<12}: {elapsed:.2f}s{timeout_mark}")
        print("=" * 52)
        session.save_report()

        if session.quit_early:
            pytest.exit("Tester quit early")

        failed = session.failed_steps()
        if failed:
            pytest.fail(
                f"{len(failed)} step(s) failed: "
                + "; ".join(s.instruction for s in failed)
            )
