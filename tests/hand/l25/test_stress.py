"""Stress tests: binary search for minimum polling interval on L25."""

import random
import threading
import time

import pytest

from linkerbot import L25
from linkerbot.hand.l25 import AngleEvent, ForceSensorEvent, SensorSource

pytestmark = [pytest.mark.l25, pytest.mark.stress]

# ── Configurable parameters ───────────────────────────────────────────────────
N_GROUPS = 3  # Number of independent binary search runs per test
WINDOW_SEC = 2.0  # Collection window per binary-search point (seconds)
SUCCESS_RATIO = 0.85  # Minimum ratio of received/expected events to pass
BINARY_SEARCH_ITERS = 10  # Bisection iterations per group
ANGLE_SEARCH_HIGH_SEC = 0.2  # Upper bound for ANGLE-only search (seconds)
FS_SEARCH_HIGH_SEC = 2.0  # Upper bound for FORCE_SENSOR search (seconds)

# ── Interleaved-read stress parameters ────────────────────────────────────────
INTERLEAVE_WINDOW_SEC = 5.0  # Duration to run polling + interleaved reads
SPEED_READ_INTERVAL_MIN_SEC = 0.05  # Minimum random gap between speed reads
SPEED_READ_INTERVAL_MAX_SEC = 0.20  # Maximum random gap between speed reads
SPEED_READ_TIMEOUT_MS = 300  # Blocking timeout per speed read attempt
POLLING_WARMUP_SEC = 0.5  # Warmup delay after start_polling() to stabilize
POLLING_COOLDOWN_SEC = 0.5  # Drain delay after stop_polling() before next start


# ── Core helpers ──────────────────────────────────────────────────────────────


def _collect(
    hand: L25,
    sources: list[SensorSource],
    interval_sec: float,
    window_sec: float,
) -> dict[str, tuple[int, int]]:
    """
    Poll `sources` at `interval_sec` for `window_sec` seconds via stream.
    Returns {source_name: (received_events, expected_events)}.
    """
    hand.start_polling({s: interval_sec for s in sources})
    time.sleep(POLLING_WARMUP_SEC)
    queue = hand.stream()
    counts: dict[str, int] = {s.value: 0 for s in sources}

    timer = threading.Timer(window_sec, hand.stop_stream)
    timer.start()
    try:
        for event in queue:
            if isinstance(event, AngleEvent) and SensorSource.ANGLE in sources:
                counts[SensorSource.ANGLE.value] += 1
            elif (
                isinstance(event, ForceSensorEvent)
                and SensorSource.FORCE_SENSOR in sources
            ):
                counts[SensorSource.FORCE_SENSOR.value] += 1
    finally:
        timer.cancel()
        hand.stop_stream()
        hand.stop_polling()

    expected = max(1, int(window_sec / interval_sec))
    time.sleep(POLLING_COOLDOWN_SEC)
    return {s.value: (counts[s.value], expected) for s in sources}


def _passes(results: dict[str, tuple[int, int]]) -> bool:
    """True if ALL sources achieved >= SUCCESS_RATIO of expected events."""
    return all(recv >= exp * SUCCESS_RATIO for recv, exp in results.values())


def _binary_search(
    hand: L25,
    sources: list[SensorSource],
    search_high_sec: float,
) -> float:
    """Binary search for minimum interval (seconds) where no data loss is detected."""
    low_sec = 0.001
    high_sec = search_high_sec

    # Verify the upper bound passes before bisecting
    results = _collect(hand, sources, high_sec, WINDOW_SEC)
    if not _passes(results):
        print(
            f"\n  WARNING: upper bound {high_sec * 1000:.0f}ms fails — check hardware"
        )
        return high_sec

    for i in range(BINARY_SEARCH_ITERS):
        mid = (low_sec + high_sec) / 2.0
        results = _collect(hand, sources, mid, WINDOW_SEC)
        passed = _passes(results)

        detail = "  ".join(
            f"{name}={recv}/{exp}" for name, (recv, exp) in results.items()
        )
        status = "PASS" if passed else "FAIL"
        print(
            f"  [{i + 1:2d}/{BINARY_SEARCH_ITERS}]  "
            f"interval={mid * 1000:8.2f}ms  {status}  "
            f"[{detail}]  "
            f"range=[{low_sec * 1000:.2f},{high_sec * 1000:.2f}]ms"
        )

        if passed:
            high_sec = mid
        else:
            low_sec = mid

    return high_sec


def _run_groups(
    hand: L25,
    sources: list[SensorSource],
    search_high_sec: float,
    label: str,
) -> None:
    """Run N_GROUPS independent binary searches and print summary."""
    results: list[float] = []
    for g in range(1, N_GROUPS + 1):
        print(f"\n── Group {g}/{N_GROUPS}: {label} " + "─" * 36)
        min_sec = _binary_search(hand, sources, search_high_sec)
        results.append(min_sec)
        print(f"  => minimum interval: {min_sec * 1000:.2f}ms")

    avg = sum(results) / len(results)
    print("\n" + "=" * 60)
    print(f"  {label} — Summary")
    print("=" * 60)
    for i, r in enumerate(results, 1):
        print(f"  Group {i}: {r * 1000:.2f}ms")
    print(f"  Average: {avg * 1000:.2f}ms")
    print("=" * 60)


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestPollingIntervalStress:
    """Binary search for minimum polling interval without data loss."""

    def test_angle_interval(self, l25_hand: L25):
        """Find minimum safe interval for ANGLE polling."""
        _run_groups(
            l25_hand,
            [SensorSource.ANGLE],
            ANGLE_SEARCH_HIGH_SEC,
            "ANGLE",
        )

    def test_force_sensor_interval(self, l25_hand: L25):
        """Find minimum safe interval for FORCE_SENSOR polling."""
        _run_groups(
            l25_hand,
            [SensorSource.FORCE_SENSOR],
            FS_SEARCH_HIGH_SEC,
            "FORCE_SENSOR",
        )

    def test_combined_interval(self, l25_hand: L25):
        """Find minimum safe interval when polling ANGLE + FORCE_SENSOR simultaneously."""
        _run_groups(
            l25_hand,
            [SensorSource.ANGLE, SensorSource.FORCE_SENSOR],
            FS_SEARCH_HIGH_SEC,
            "ANGLE+FORCE_SENSOR",
        )


# ── Interleaved read stress ──────────────────────────────────────────────────


class TestInterleavedReadDuringPolling:
    """Test that blocking reads work reliably while polling is active.

    Uses default polling (ANGLE@60Hz + FORCE_SENSOR@30Hz) and randomly
    interleaves blocking speed reads to verify no frame collisions.
    """

    def test_speed_read_during_polling(self, l25_hand: L25):
        """Randomly issue speed.get_blocking() while default polling is running.

        Default polling (ANGLE@60Hz, FORCE_SENSOR@30Hz) is auto-started.
        This test sends blocking speed reads at random intervals and checks
        that the majority succeed without timeout, validating that polling
        and ad-hoc reads can coexist on the CAN bus.
        """
        hand = l25_hand

        # Default polling is already active from __init__; restart to be explicit
        hand.start_polling()
        time.sleep(POLLING_WARMUP_SEC)

        total_sent = 0
        total_ok = 0
        total_timeout = 0
        latencies: list[float] = []

        deadline = time.monotonic() + INTERLEAVE_WINDOW_SEC
        print(f"\n  Running interleaved speed reads for {INTERLEAVE_WINDOW_SEC}s ...")
        print(
            f"  Polling: ANGLE@60Hz + FORCE_SENSOR@30Hz  |  "
            f"Speed read timeout: {SPEED_READ_TIMEOUT_MS}ms"
        )

        while time.monotonic() < deadline:
            gap = random.uniform(
                SPEED_READ_INTERVAL_MIN_SEC, SPEED_READ_INTERVAL_MAX_SEC
            )
            time.sleep(gap)

            total_sent += 1
            t0 = time.monotonic()
            try:
                hand.speed.get_blocking(timeout_ms=SPEED_READ_TIMEOUT_MS)
                elapsed_ms = (time.monotonic() - t0) * 1000
                total_ok += 1
                latencies.append(elapsed_ms)
            except TimeoutError:
                elapsed_ms = (time.monotonic() - t0) * 1000
                total_timeout += 1
                print(f"    TIMEOUT on read #{total_sent} ({elapsed_ms:.1f}ms)")

        hand.stop_polling()

        # ── Report ────────────────────────────────────────────────────────
        success_rate = total_ok / total_sent if total_sent else 0.0
        avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
        max_latency = max(latencies) if latencies else 0.0

        print(f"\n  {'=' * 56}")
        print("  Interleaved Speed Read — Results")
        print(f"  {'=' * 56}")
        print(f"  Total sent:     {total_sent}")
        print(f"  Succeeded:      {total_ok}")
        print(f"  Timed out:      {total_timeout}")
        print(f"  Success rate:   {success_rate:.1%}")
        print(f"  Avg latency:    {avg_latency:.1f}ms")
        print(f"  Max latency:    {max_latency:.1f}ms")
        print(f"  {'=' * 56}")

        assert total_sent > 0, "No speed reads were sent"
        assert success_rate >= SUCCESS_RATIO, (
            f"Speed read success rate {success_rate:.1%} < {SUCCESS_RATIO:.0%}: "
            f"{total_timeout}/{total_sent} timed out"
        )
