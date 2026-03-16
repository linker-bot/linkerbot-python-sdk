"""Tests for L25 TorqueManager with hardware."""

import threading
import time

import pytest

from linkerbot import L25
from linkerbot.hand.l25 import AngleEvent, L25Torque, SensorSource
from tests.conftest import InteractiveSession

pytestmark = [pytest.mark.l25, pytest.mark.control]

TOLERANCE = 3.0
MOTION_TIMEOUT_SEC = 20.0
_POLLING_INTERVAL_SEC = 0.4

# Hardware-verified poses
OPEN = [
    100.0,
    100.0,
    100.0,
    100.0,  # thumb
    100.0,
    100.0,
    100.0,  # index
    67.0,
    100.0,
    100.0,  # middle
    33.0,
    100.0,
    100.0,  # ring
    0.0,
    100.0,
    100.0,  # pinky
]
CLOSED = [
    100.0,
    50.0,
    55.0,
    55.0,  # thumb
    50.0,
    0.0,
    0.0,  # index
    50.0,
    0.0,
    0.0,  # middle
    50.0,
    0.0,
    0.0,  # ring
    50.0,
    0.0,
    0.0,  # pinky
]


def _move_and_time(
    hand: L25,
    target: list[float],
    tolerance: float = TOLERANCE,
    timeout_sec: float = MOTION_TIMEOUT_SEC,
) -> tuple[float, bool]:
    """Set target angles, stream until within tolerance, return (elapsed_seconds, timed_out)."""
    timed_out = False
    hand.start_polling({SensorSource.ANGLE: _POLLING_INTERVAL_SEC})
    queue = hand.stream()
    hand.angle.set_angles(
        target
    )  # HACK: set_angles after stream() may race with polling
    start = time.perf_counter()
    deadline = start + timeout_sec
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

    def test_get_blocking_returns_valid_data(self, l25_hand: L25):
        """Blocking read should return 16 torque values."""
        data = l25_hand.torque.get_blocking(timeout_ms=500)
        assert data is not None
        assert len(data.torques) == 16
        print(f"\n  Torques: {[f'{t:.1f}' for t in data.torques.to_list()]}")

    def test_get_blocking_has_timestamp(self, l25_hand: L25):
        """Torque data should have a valid timestamp."""
        data = l25_hand.torque.get_blocking(timeout_ms=500)
        assert data.timestamp > 0
        assert data.timestamp <= time.time()

    def test_set_torques_with_list(self, l25_hand: L25):
        """set_torques should accept list[float] without error."""
        l25_hand.torque.set_torques([50.0] * 16)

    def test_set_torques_with_l25_torque(self, l25_hand: L25):
        """set_torques should accept L25Torque instance without error."""
        l25_hand.torque.set_torques(L25Torque.from_list([50.0] * 16))


class TestTorqueManagerSnapshot:
    """Test TorqueManager snapshot mode."""

    def test_snapshot_populated_after_read(self, l25_hand: L25):
        """get_snapshot should return non-None after blocking read."""
        l25_hand.torque.get_blocking(timeout_ms=500)
        data = l25_hand.torque.get_snapshot()
        assert data is not None
        assert len(data.torques) == 16


@pytest.mark.interactive
class TestTorqueInteractive:
    """Interactive tests for verifying torque affects grip strength."""

    def test_torque_levels(
        self, l25_hand: L25, interactive_session: InteractiveSession
    ):
        """Verify low/mid/high torque visibly affects grip strength."""
        session = interactive_session
        motion_results: list[tuple[str, float, bool]] = []

        # Set speed to max for consistent observation
        l25_hand.speed.set_speeds([100.0] * 16)

        def track(label: str, target: list[float]) -> None:
            elapsed, timed_out = _move_and_time(l25_hand, target)
            motion_results.append((label, elapsed, timed_out))

        for level, torque_val in [("LOW", 10.0), ("MID", 50.0), ("HIGH", 100.0)]:
            # Close grip
            session.step(
                instruction=f"[{level} torque={torque_val}] Closing grip",
                action=lambda lbl=f"{level} close", tv=torque_val: (
                    l25_hand.torque.set_torques([tv] * 16),
                    track(lbl, CLOSED),
                ),
                expected=(
                    f"Fingers close with {level} torque "
                    f"(should feel {'weak' if level == 'LOW' else 'medium' if level == 'MID' else 'strong'})"
                ),
            )

            # Open hand
            session.step(
                instruction=f"[{level} torque={torque_val}] Opening hand",
                action=lambda lbl=f"{level} open": (track(lbl, OPEN),),
                expected="Fingers fully open",
            )

        session.run()

        _move_and_time(l25_hand, OPEN)

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
