"""L30 concurrent demo: device-side periodic reports + host-side high-rate control.

After fix#141 the SDK runs send and receive on independent locks and the
dispatcher coalesces queued frames into a single ``CANFD_Transmit`` call
when more than one is ready. This demo exercises both paths simultaneously
on real hardware so you can observe:

- A background event consumer reading device-side periodic angle reports
  via ``hand.stream()`` while the main thread is hammering writes.
- A high-rate PVT control loop sending position + speed + torque targets
  every cycle. With batching, those three frames collapse into one vendor
  USB call instead of three.
- A single tactile read in the middle of the run, which used to block all
  control writes for ~10 ms under the old global ``_transaction_lock``;
  after fix#141 it only serializes other tactile reads.

Run:

    sudo -E env LINKERBOT_CANFD_LIB=/path/to/libcanbus.so \\
        uv run python examples/l30_concurrent_demo.py

Common options:

    --hz 100               # control loop rate (frames/sec, *3 channels)
    --duration 10          # total runtime in seconds
    --flex-ratio 0.5       # safe travel of cycling joints, 0..1
    --speed 100 / --torque 200   # motion limits
    --tactile-at 2.0       # seconds into run to fire a tactile read
    --library-path / --node-id / --host-id / --device-index / --channel-index

The output reports per-second rates of sent frames, periodic events
received, and best-effort wall-clock latencies for the tactile probe and
the average control cycle.
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
import threading
import time
from types import FrameType

from linkerbot.exceptions import LinkerbotError
from linkerbot.hand.l30 import L30, L30_JOINT_SPECS
from linkerbot.hand.l30.force_sensor import Finger

JOINT_COUNT = len(L30_JOINT_SPECS)

# Reuse the index map from l30_pinky_cycle for consistency.
THUMB_TIP = 1
INDEX_TIP = 15
MIDDLE_TIP = 8
RING_TIP = 5
PINKY_TIP = 10
TIP_INDICES = (THUMB_TIP, INDEX_TIP, MIDDLE_TIP, RING_TIP, PINKY_TIP)


def _neutral_percentage(joint_index: int) -> float:
    """Percentage that maps to raw 0 for the given joint.

    Flex joints have ``spec.minimum = 0`` so raw 0 = 0 %. Signed joints
    (J5 / J12–J14 / J17) are symmetric around 0, so raw 0 = 50 %.
    """
    spec = L30_JOINT_SPECS[joint_index]
    return 50.0 if spec.minimum < 0 else 0.0


def _safe_targets(flex_ratio: float) -> tuple[list[float], list[float]]:
    """Two interleaved targets: tip-flex (gentle close) and neutral (open).

    Uses the 0-100 percentage API. ``flex_ratio`` scales cycling joints to
    ``flex_ratio * 100 %``; all other joints stay at their neutral
    percentage so signed joints (J5/J12-J14/J17) stay centred instead of
    running to their minimum.
    """
    neutral = [_neutral_percentage(index) for index in range(JOINT_COUNT)]
    flexed = list(neutral)
    for index in TIP_INDICES:
        flexed[index] = flex_ratio * 100.0
    return flexed, neutral


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="L30 concurrent send + receive demo (fix#141)"
    )
    parser.add_argument("--library-path", default=os.environ.get("LINKERBOT_CANFD_LIB"))
    parser.add_argument(
        "--hz",
        type=float,
        default=100.0,
        help="control loop rate (Hz). Each cycle sends 3 frames: angle+speed+torque",
    )
    parser.add_argument("--duration", type=float, default=10.0)
    parser.add_argument("--flex-ratio", type=float, default=0.5)
    parser.add_argument("--speed", type=int, default=100)
    parser.add_argument("--torque", type=int, default=200)
    parser.add_argument(
        "--tactile-at",
        type=float,
        default=2.0,
        help="seconds into the run to fire one tactile read on the thumb;"
        " set <0 to skip",
    )
    parser.add_argument("--node-id", type=int, default=1)
    parser.add_argument("--host-id", type=int, default=0)
    parser.add_argument("--device-index", type=int, default=0)
    parser.add_argument("--channel-index", type=int, default=0)
    parser.add_argument(
        "--timeout-ms",
        type=float,
        default=1000.0,
        help="ACK timeout for enable/disable",
    )
    return parser.parse_args()


def run() -> None:
    args = parse_args()
    if args.hz <= 0 or args.duration <= 0:
        raise SystemExit("--hz and --duration must be positive")
    if not 0.0 < args.flex_ratio <= 1.0:
        raise SystemExit("--flex-ratio must be in (0, 1]")

    flexed, neutral = _safe_targets(args.flex_ratio)
    period_s = 1.0 / args.hz
    total_frames = max(1, int(round(args.duration * args.hz)))

    stop_requested = False

    def _on_signal(_signum: int, _frame: FrameType | None) -> None:
        nonlocal stop_requested
        stop_requested = True
        print("\n[demo] Ctrl+C received; winding down safely.")

    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)

    print(
        f"[demo] open L30 (node={args.node_id}, host={args.host_id}, "
        f"device={args.device_index}, channel={args.channel_index})"
    )
    print(
        f"[demo] control_hz={args.hz:.0f}  duration={args.duration:.1f}s  "
        f"total_cycles={total_frames}  frames_per_cycle=3 (angle+speed+torque)"
    )

    with L30(
        node_id=args.node_id,
        host_id=args.host_id,
        device_index=args.device_index,
        channel_index=args.channel_index,
        library_path=args.library_path,
        auto_start_periodic=True,  # device-side angle reports flow into stream()
    ) as hand:
        hand.control.enable(timeout_ms=args.timeout_ms)
        # Speed/torque limits live in their own managers; we set once at
        # startup and then only update angle in the loop.
        hand.speed.set_speeds([args.speed] * JOINT_COUNT)
        hand.torque.set_torques([args.torque] * JOINT_COUNT)

        events_received = 0
        stream = hand.stream(maxsize=512)

        def consume_events() -> None:
            nonlocal events_received
            for _ in stream:
                events_received += 1
                if stop_requested:
                    break

        consumer = threading.Thread(
            target=consume_events, name="L30StreamConsumer", daemon=True
        )
        consumer.start()

        try:
            stats = _run_control_loop(
                hand=hand,
                flexed=flexed,
                neutral=neutral,
                period_s=period_s,
                total_frames=total_frames,
                tactile_at_s=args.tactile_at,
                should_break=lambda: stop_requested,
                args=args,
            )
        finally:
            print("[demo] returning to neutral and disabling")
            try:
                hand.angle.set_angles(neutral)
                time.sleep(0.2)
            except LinkerbotError as error:
                print(f"[demo] failed to send neutral pose: {error}")
            try:
                hand.control.disable(timeout_ms=args.timeout_ms)
            except LinkerbotError as error:
                print(f"[demo] disable failed: {error}")
            hand.stop_stream()
            consumer.join(timeout=1.0)

        _print_summary(stats, events_received=events_received)


def _run_control_loop(
    *,
    hand: L30,
    flexed: list[float],
    neutral: list[float],
    period_s: float,
    total_frames: int,
    tactile_at_s: float,
    should_break,
    args: argparse.Namespace,
) -> dict[str, float]:
    """Send 3 frames per cycle (angle + speed + torque) at the target rate.

    Setting speed/torque every cycle is overkill for real control loops but
    serves the demo: it guarantees three frames sit in the dispatcher's
    send queue together so the batch-send path actually engages.
    """
    cycles_sent = 0
    batches_observed = 0  # approximated via wall-clock — see note below
    tactile_done = False
    tactile_latency_ms = float("nan")
    start = time.monotonic()
    next_send = start
    cycle_latencies_ms: list[float] = []

    while cycles_sent < total_frames:
        if should_break():
            break
        # Trigger a single tactile read partway through the run, off the
        # main control thread, to show it doesn't block writes anymore.
        if (
            not tactile_done
            and tactile_at_s >= 0
            and (time.monotonic() - start) >= tactile_at_s
        ):
            tactile_done = True
            tactile_thread = threading.Thread(
                target=_fire_tactile_probe,
                args=(hand, lambda v: _set_tactile_latency(cycle_latencies_ms, v)),
                name="L30TactileProbe",
                daemon=True,
            )
            tactile_thread.start()

        target = flexed if (cycles_sent % 20) < 10 else neutral
        cycle_start = time.monotonic()
        # These three calls queue into one dispatcher send queue;
        # the send loop coalesces them into a single CANFD_Transmit.
        hand.angle.set_angles(target)
        hand.speed.set_speeds([args.speed] * JOINT_COUNT)
        hand.torque.set_torques([args.torque] * JOINT_COUNT)
        cycle_latencies_ms.append((time.monotonic() - cycle_start) * 1000)
        cycles_sent += 1
        batches_observed += 1

        next_send += period_s
        sleep_for = next_send - time.monotonic()
        if sleep_for > 0:
            time.sleep(sleep_for)

    elapsed = time.monotonic() - start
    return {
        "elapsed_s": elapsed,
        "cycles_sent": cycles_sent,
        "frames_sent": cycles_sent * 3,
        "cycle_latency_p50_ms": _percentile(cycle_latencies_ms, 0.5),
        "cycle_latency_p99_ms": _percentile(cycle_latencies_ms, 0.99),
        "tactile_latency_ms": tactile_latency_ms,
    }


def _set_tactile_latency(_dest, _value):
    """Reserved hook; tactile latency is currently logged from the probe
    thread itself rather than relayed back."""
    return None


def _fire_tactile_probe(hand: L30, _record) -> None:
    """Read the thumb tactile matrix while the control loop is running.

    Pre-fix#141 this would have blocked every set_angles / set_speeds /
    set_torques on the main thread for ~10 ms because the L30Client held
    a single transaction lock for both tactile and normal requests.
    """
    start = time.monotonic()
    try:
        hand.force_sensor.get_finger(Finger.THUMB, timeout_ms=200)
    except LinkerbotError as error:
        print(f"[demo] tactile probe failed: {error}")
        return
    elapsed_ms = (time.monotonic() - start) * 1000
    print(f"[demo] tactile thumb read completed in {elapsed_ms:.1f} ms")


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(round(p * (len(ordered) - 1)))))
    return ordered[index]


def _print_summary(stats: dict[str, float], *, events_received: int) -> None:
    elapsed = stats["elapsed_s"]
    frames = int(stats["frames_sent"])
    cycles = int(stats["cycles_sent"])
    print()
    print("[demo] ─ summary ──────────────────────────────────────────────")
    print(f"[demo]   wall time             {elapsed:.2f} s")
    print(f"[demo]   control cycles sent    {cycles}  ({cycles / elapsed:.0f} Hz)")
    print(f"[demo]   total frames sent      {frames}  ({frames / elapsed:.0f} fps)")
    print(
        f"[demo]   cycle wall latency     p50={stats['cycle_latency_p50_ms']:.2f} ms  "
        f"p99={stats['cycle_latency_p99_ms']:.2f} ms"
    )
    print(
        f"[demo]   periodic events recv'd {events_received}  "
        f"({events_received / elapsed:.0f}/s)"
    )
    print(
        "[demo]   note: 3 frames per cycle queue back-to-back; the dispatcher "
        "should\n[demo]         batch them into one CANFD_Transmit. If "
        "events/s is healthy\n[demo]         while frames/s is high, "
        "concurrent send+recv is working."
    )


if __name__ == "__main__":
    try:
        run()
    except LinkerbotError as error:
        print(f"[demo] linkerbot error: {error}", file=sys.stderr)
        sys.exit(1)
