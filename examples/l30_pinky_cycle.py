"""L30 demo: cycle tip-flex / tip-extend / MCP-flex / MCP-restore.

Sends a configurable rate of ``set_angles()`` calls for a configurable total
duration. The four poses are interleaved frame-by-frame rather than played
sequentially, so at ``--hz 60 --duration 5`` you get 300 frames where the
target rotates through ``[tip-flex, tip-extend, MCP-flex, MCP-restore]`` on
every frame. Useful as a visual demo and a quick smoke test for high-rate
``set_angles`` throughput.

Run:

    sudo -E env LINKERBOT_CANFD_LIB=/path/to/libcanbus.so \\
        uv run python examples/l30_pinky_cycle.py

Common options:

    --hz 60                # send rate (frames per second)
    --duration 5           # total runtime in seconds
    --flex-ratio 0.9       # how far to flex (1.0 = up to documented max; default 0.9)
    --speed 250 / --torque 800
    --frame-type 0x04      # CAN FD without BRS (default); 0x0C enables BRS
    --library-path / --node-id / --host-id / --device-index / --channel-index
    --timeout-ms 1000      # ACK timeout for enable/disable

Frame N (zero-based) carries pose ``N mod 4``:

    pose 0  指尖弯曲   (tip flex)      — J2 / J6 / J9 / J11 / J16 → flex_ratio × max
    pose 1  指尖张开   (tip extend)    — all zeros (neutral)
    pose 2  指根弯曲   (MCP flex)      — J1 / J7 / J8 / J10 / J15 → flex_ratio × max
    pose 3  指根复原   (MCP restore)   — all zeros (neutral)

Joint indices follow the L30 left-hand table:

    J1  thumb MCP            J7  ring MCP             J13 middle abduction
    J2  thumb tip            J8  middle MCP           J14 index abduction
    J3  thumb abduction      J9  middle tip           J15 index MCP
    J4  thumb rotation       J10 pinky MCP            J16 index tip
    J5  ring abduction       J11 pinky tip            J17 wrist
    J6  ring tip             J12 pinky abduction
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
import time
from types import FrameType

from linkerbot.exceptions import LinkerbotError
from linkerbot.hand.l30 import L30, L30_JOINT_SPECS

JOINT_COUNT = len(L30_JOINT_SPECS)

# ---------------------------------------------------------------------------
# Joint indices (zero-based) per the L30 left-hand mapping. Adjust if your
# hardware differs from the reference table.
# ---------------------------------------------------------------------------
THUMB_MCP = 0  # J1  : 拇指指根弯曲
THUMB_TIP = 1  # J2  : 拇指指尖弯曲
RING_TIP = 5  # J6  : 无名指指尖弯曲
RING_MCP = 6  # J7  : 无名指指根弯曲
MIDDLE_MCP = 7  # J8  : 中指指根弯曲
MIDDLE_TIP = 8  # J9  : 中指指尖弯曲
PINKY_MCP = 9  # J10 : 小指指根弯曲
PINKY_TIP = 10  # J11 : 小指指尖弯曲
INDEX_MCP = 14  # J15 : 食指指根弯曲
INDEX_TIP = 15  # J16 : 食指指尖弯曲

TIP_INDICES = (THUMB_TIP, INDEX_TIP, MIDDLE_TIP, RING_TIP, PINKY_TIP)
MCP_INDICES = (THUMB_MCP, INDEX_MCP, MIDDLE_MCP, RING_MCP, PINKY_MCP)


def _neutral_percentage(joint_index: int) -> float:
    """Percentage that maps to raw 0 for the given joint.

    Flex joints have ``spec.minimum = 0`` so raw 0 = 0 %. Signed joints
    (J5 / J12–J14 / J17) are symmetric around 0, so raw 0 = 50 %.
    """
    spec = L30_JOINT_SPECS[joint_index]
    return 50.0 if spec.minimum < 0 else 0.0


def make_target(
    active_indices: tuple[int, ...], flex_ratio: float
) -> list[int | float]:
    """Build a 17-value percentage target list (aligned with L6 API).

    Non-active joints stay at their neutral percentage (0 % for flex joints,
    50 % for symmetric signed joints — both map to raw 0). Active joints
    are pushed to ``flex_ratio * 100`` percent, which for flex joints
    corresponds to ``round(spec.maximum * flex_ratio)`` raw units.
    """
    target: list[int | float] = [
        _neutral_percentage(index) for index in range(JOINT_COUNT)
    ]
    for index in active_indices:
        target[index] = flex_ratio * 100.0
    return target


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="L30 tip / MCP flex-extend cycle demo")
    parser.add_argument("--library-path", default=os.environ.get("LINKERBOT_CANFD_LIB"))
    parser.add_argument(
        "--hz",
        type=float,
        default=5.0,
        help="send rate within each phase (frames per second)",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=5.0,
        help="total runtime in seconds, split equally across 4 poses",
    )
    parser.add_argument(
        "--flex-ratio",
        type=float,
        default=0.9,
        help="how far to flex active joints, 0..1 (default 0.9)",
    )
    parser.add_argument(
        "--speed", type=int, default=250, help="value passed to set_speeds (1..250)"
    )
    parser.add_argument(
        "--torque", type=int, default=800, help="value passed to set_torques (60..800)"
    )
    parser.add_argument("--node-id", type=int, default=1)
    parser.add_argument("--host-id", type=int, default=0)
    parser.add_argument("--device-index", type=int, default=0)
    parser.add_argument("--channel-index", type=int, default=0)
    parser.add_argument(
        "--frame-type",
        type=_auto_int,
        default=0x04,
        help="outgoing frame type: 0x04=CAN FD without BRS, 0x0C=CAN FD+BRS",
    )
    parser.add_argument(
        "--timeout-ms",
        type=float,
        default=1000.0,
        help="ACK timeout for enable/disable; SDK default 100ms is too short on real hardware.",
    )
    return parser.parse_args()


def run() -> None:
    args = parse_args()
    if args.hz <= 0:
        raise SystemExit("--hz must be positive")
    if args.duration <= 0:
        raise SystemExit("--duration must be positive")
    if not 0.0 < args.flex_ratio <= 1.0:
        raise SystemExit("--flex-ratio must be in (0, 1]")

    neutral: list[int | float] = [
        _neutral_percentage(index) for index in range(JOINT_COUNT)
    ]
    tip_flex_target = make_target(TIP_INDICES, args.flex_ratio)
    mcp_flex_target = make_target(MCP_INDICES, args.flex_ratio)

    poses = (
        ("指尖弯曲 (tip flex)   ", tip_flex_target),
        ("指尖张开 (tip extend) ", neutral),
        ("指根弯曲 (MCP flex)   ", mcp_flex_target),
        ("指根复原 (MCP restore)", neutral),
    )
    pose_count = len(poses)

    frame_period = 1.0 / args.hz
    total_frames = max(1, int(round(args.duration * args.hz)))

    stop_requested = False

    def _on_signal(_signum: int, _frame: FrameType | None) -> None:
        nonlocal stop_requested
        stop_requested = True
        print("\n[demo] Ctrl+C received; finishing safely.")

    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)

    print(
        f"[demo] open L30 (node_id={args.node_id}, host_id={args.host_id}, "
        f"device={args.device_index}, channel={args.channel_index}, "
        f"frame_type=0x{args.frame_type:02X})"
    )
    print(
        f"[demo] hz={args.hz:.0f}  duration={args.duration:.2f}s  "
        f"total_frames={total_frames}  poses cycle every {pose_count} frames "
        f"(period {pose_count * frame_period * 1000:.0f}ms)"
    )

    with L30(
        node_id=args.node_id,
        host_id=args.host_id,
        device_index=args.device_index,
        channel_index=args.channel_index,
        library_path=args.library_path,
        frame_type=args.frame_type,
        auto_start_periodic=False,  # 关掉默认周期上报，发送节奏更稳
    ) as hand:
        print(
            f"[demo] enabling motors, speed={args.speed}, torque={args.torque}, "
            f"timeout_ms={args.timeout_ms:.0f}"
        )
        hand.control.enable(timeout_ms=args.timeout_ms)
        hand.speed.set_speeds([args.speed] * JOINT_COUNT)
        hand.torque.set_torques([args.torque] * JOINT_COUNT)

        try:
            _run_interleaved(
                hand=hand,
                poses=poses,
                total_frames=total_frames,
                frame_period=frame_period,
                should_break=lambda: stop_requested,
            )
        finally:
            print("[demo] returning to neutral and disabling")
            try:
                hand.angle.set_angles(neutral)
                _sleep(0.3, lambda: False)
            except LinkerbotError as error:
                print(f"[demo] failed to send neutral pose: {error}")
            try:
                hand.control.disable(timeout_ms=args.timeout_ms)
            except LinkerbotError as error:
                print(f"[demo] disable failed: {error}")


def _run_interleaved(
    *,
    hand: L30,
    poses: tuple[tuple[str, list[int | float]], ...],
    total_frames: int,
    frame_period: float,
    should_break,
) -> None:
    """Send ``total_frames`` frames at the configured rate, with the pose
    selected by ``frame_index % len(poses)`` so the four targets interleave
    one frame at a time rather than running sequentially in big blocks.
    """
    pose_count = len(poses)
    counts = [0] * pose_count
    start = time.monotonic()
    next_send = start
    sent = 0
    for frame_index in range(total_frames):
        if should_break():
            break
        label, target = poses[frame_index % pose_count]
        hand.angle.set_angles(target)
        counts[frame_index % pose_count] += 1
        sent += 1
        next_send += frame_period
        sleep_for = next_send - time.monotonic()
        if sleep_for > 0:
            time.sleep(sleep_for)
    elapsed = time.monotonic() - start
    actual_hz = sent / elapsed if elapsed > 0 else 0.0
    print(f"[demo] sent {sent} frames in {elapsed:.2f}s (≈ {actual_hz:.1f} Hz)")
    for (label, _), count in zip(poses, counts, strict=True):
        print(f"[demo]   {label}  × {count}")


def _sleep(seconds: float, should_break) -> None:
    deadline = time.monotonic() + seconds
    while not should_break():
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 0.05))


def _auto_int(value: str) -> int:
    return int(value, 0)


if __name__ == "__main__":
    try:
        run()
    except LinkerbotError as error:
        print(f"[demo] linkerbot error: {error}", file=sys.stderr)
        sys.exit(1)
