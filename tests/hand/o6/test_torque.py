"""Tests for O6 TorqueManager with hardware."""

import threading
import time

import pytest

from linkerbot import O6
from linkerbot.hand.o6 import AngleEvent, O6Torque, SensorSource
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
    data = hand.angle.get_snapshot()
    print(
        f"\n  Motion time: {elapsed:.2f}s | "
        f"Angles: {[f'{a:.1f}' for a in data.angles.to_list()] if data else 'N/A'}"
    )
    return elapsed, timed_out


class TestTorqueManagerBlocking:
    """Test TorqueManager blocking read."""

    def test_get_blocking_returns_valid_data(self, o6_hand: O6):
        """Blocking read should return 6 torque values."""
        data = o6_hand.torque.get_blocking(timeout_ms=500)
        assert data is not None
        assert len(data.torques) == 6
        print(f"\n  Torques: {[f'{t:.1f}' for t in data.torques.to_list()]}")

    def test_get_blocking_has_timestamp(self, o6_hand: O6):
        """Torque data should have a valid timestamp."""
        data = o6_hand.torque.get_blocking(timeout_ms=500)
        assert data.timestamp > 0
        assert data.timestamp <= time.time()

    def test_set_torques_with_list(self, o6_hand: O6):
        """set_torques should accept list[float] without error."""
        o6_hand.torque.set_torques([50.0] * 6)

    def test_set_torques_with_o6_torque(self, o6_hand: O6):
        """set_torques should accept O6Torque instance without error."""
        o6_hand.torque.set_torques(O6Torque.from_list([50.0] * 6))


class TestTorqueManagerSnapshot:
    """Test TorqueManager snapshot mode."""

    def test_snapshot_populated_after_read(self, o6_hand: O6):
        """get_snapshot should return non-None after blocking read."""
        o6_hand.torque.get_blocking(timeout_ms=500)
        data = o6_hand.torque.get_snapshot()
        assert data is not None
        assert len(data.torques) == 6


@pytest.mark.interactive
class TestTorqueInteractive:
    """Interactive tests for verifying torque affects grip strength."""

    def test_torque_levels(self, o6_hand: O6, interactive_session: InteractiveSession):
        """Verify low/mid/high torque visibly affects grip strength."""
        session = interactive_session
        motion_results: list[tuple[str, float, bool]] = []

        # Set speed and acceleration to max for consistent observation
        o6_hand.speed.set_speeds([100.0] * 6)
        o6_hand.acceleration.set_accelerations([100.0] * 6)

        def track(label: str, target: list[float]) -> None:
            elapsed, timed_out = _move_and_time(o6_hand, target)
            motion_results.append((label, elapsed, timed_out))

        for level, torque_val in [("LOW", 10.0), ("MID", 50.0), ("HIGH", 100.0)]:
            session.step(
                instruction=f"[{level} torque={torque_val}] Closing grip",
                action=lambda lbl=f"{level} close", tv=torque_val: (
                    o6_hand.torque.set_torques([tv] * 6),
                    track(lbl, CLOSED),
                ),
                expected=(
                    f"Fingers close with {level} torque "
                    f"(should feel {'weak' if level == 'LOW' else 'medium' if level == 'MID' else 'strong'})"
                ),
            )

            session.step(
                instruction=f"[{level} torque={torque_val}] Opening hand",
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
