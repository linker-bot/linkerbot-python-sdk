"""Enable a P7, move one joint by a small angle, and return to the start.

Run these commands from the SDK repository root to install the local source:

    python3 -m venv .venv
    . .venv/bin/activate
    python -m pip install -e '.[kinetix]'

Prepare a 1 Mbit/s SocketCAN interface, then run the example:

    sudo ip link set can0 down
    sudo ip link set can0 type can bitrate 1000000
    sudo ip link set can0 up
    python examples/p7_enable_small_move.py --side left --interface can0

The arm is disabled during cleanup. Keep the workspace clear and have a
hardware emergency stop or power disconnect within reach.
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from collections.abc import Sequence

from linkerbot import P7

MAX_DELTA_DEGREES = 10.0
MAX_SPEED_RAD_S = 1.0
MAX_ACCELERATION_RAD_S2 = 5.0
JOINT_COUNT = 7


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Enable a P7 and perform one small, reversible joint move."
    )
    parser.add_argument("--side", choices=("left", "right"), required=True)
    parser.add_argument(
        "--interface", default="can0", help="SocketCAN channel (default: can0)"
    )
    parser.add_argument(
        "--interface-type",
        default="socketcan",
        help="python-can backend (default: socketcan)",
    )
    parser.add_argument(
        "--joint",
        type=int,
        choices=range(1, JOINT_COUNT + 1),
        default=1,
        metavar="1..7",
        help="joint number to move (default: 1)",
    )
    parser.add_argument(
        "--delta-degrees",
        type=float,
        default=3.0,
        help=f"move magnitude in degrees, >0 and <= {MAX_DELTA_DEGREES:g}",
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=0.2,
        help=f"trajectory speed in rad/s, >0 and <= {MAX_SPEED_RAD_S:g}",
    )
    parser.add_argument(
        "--acceleration",
        type=float,
        default=1.0,
        help=(
            f"trajectory acceleration in rad/s^2, >0 and <= {MAX_ACCELERATION_RAD_S2:g}"
        ),
    )
    parser.add_argument(
        "--hold-seconds",
        type=float,
        default=1.0,
        help="time at the offset position before returning (default: 1.0)",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="skip the MOVE confirmation; only use with external safety measures",
    )
    args = parser.parse_args(argv)

    if not math.isfinite(args.delta_degrees) or not (
        0.0 < args.delta_degrees <= MAX_DELTA_DEGREES
    ):
        parser.error(f"--delta-degrees must be > 0 and <= {MAX_DELTA_DEGREES:g}")
    if not math.isfinite(args.speed) or not (0.0 < args.speed <= MAX_SPEED_RAD_S):
        parser.error(f"--speed must be > 0 and <= {MAX_SPEED_RAD_S:g}")
    if not math.isfinite(args.acceleration) or not (
        0.0 < args.acceleration <= MAX_ACCELERATION_RAD_S2
    ):
        parser.error(f"--acceleration must be > 0 and <= {MAX_ACCELERATION_RAD_S2:g}")
    if not math.isfinite(args.hold_seconds) or args.hold_seconds < 0.0:
        parser.error("--hold-seconds must be a finite value >= 0")
    return args


def choose_offset_target(
    current: float, lower: float, upper: float, delta: float
) -> float:
    """Choose the delta direction with more room inside the joint limits."""
    if not all(math.isfinite(value) for value in (current, lower, upper, delta)):
        raise ValueError("joint position, limits, and delta must be finite")
    if lower > upper or not lower <= current <= upper:
        raise ValueError(
            f"current angle {current:.6f} is outside [{lower:.6f}, {upper:.6f}]"
        )
    if delta <= 0.0:
        raise ValueError("delta must be positive")

    room_positive = upper - current
    room_negative = current - lower
    if max(room_positive, room_negative) < delta:
        raise ValueError(
            f"joint has less than {math.degrees(delta):.3f} degrees of limit margin"
        )
    direction = 1.0 if room_positive >= room_negative else -1.0
    return current + direction * delta


def confirm_motion(args: argparse.Namespace) -> None:
    if args.yes:
        return
    print("WARNING: this command energizes the P7 and moves one joint.")
    print("Clear the workspace and prepare a hardware emergency stop or power cutoff.")
    confirmation = input("Type MOVE to continue: ").strip()
    if confirmation != "MOVE":
        raise RuntimeError("motion cancelled")


def run(args: argparse.Namespace) -> None:
    confirm_motion(args)

    arm: P7 | None = None
    enable_started = False
    returned_to_start = False
    saved_velocities: list[float] | None = None
    saved_accelerations: list[float] | None = None

    try:
        print(f"Connecting to P7 {args.side} on {args.interface} ...")
        arm = P7(
            side=args.side,
            interface_name=args.interface,
            interface_type=args.interface_type,
        )
        start_angles = arm.get_angles()
        joint_limits = arm.get_joint_limits()
        joint_index = args.joint - 1
        delta_rad = math.radians(args.delta_degrees)
        target_angles = start_angles.copy()
        target_angles[joint_index] = choose_offset_target(
            start_angles[joint_index],
            joint_limits[joint_index][0],
            joint_limits[joint_index][1],
            delta_rad,
        )

        print(
            f"Joint {args.joint}: {math.degrees(start_angles[joint_index]):.2f} deg "
            f"-> {math.degrees(target_angles[joint_index]):.2f} deg"
        )
        saved_velocities = arm.get_control_velocities()
        saved_accelerations = arm.get_control_acceleration()
        arm.set_velocities([args.speed] * JOINT_COUNT)
        arm.set_accelerations([args.acceleration] * JOINT_COUNT)

        enable_started = True
        arm.enable()
        print("P7 enabled; starting the small move.")
        arm.move_j(target_angles)
        time.sleep(args.hold_seconds)
        arm.move_j(start_angles)
        returned_to_start = True
        print("P7 returned to its starting joint angles.")
    finally:
        if arm is not None:
            if enable_started and not returned_to_start:
                try:
                    arm.emergency_stop()
                except Exception as error:
                    print(
                        f"warning: failed to hold the current position: {error}",
                        file=sys.stderr,
                    )
            if saved_velocities is not None and saved_accelerations is not None:
                try:
                    arm.set_velocities(saved_velocities)
                    arm.set_accelerations(saved_accelerations)
                except Exception as error:
                    print(
                        f"warning: failed to restore motion settings: {error}",
                        file=sys.stderr,
                    )
            if enable_started:
                try:
                    arm.disable()
                    time.sleep(0.1)
                    print("P7 disabled.")
                except Exception as error:
                    print(f"warning: failed to disable P7: {error}", file=sys.stderr)
            arm.close()


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        run(args)
    except KeyboardInterrupt:
        print("\nInterrupted; cleanup requested.", file=sys.stderr)
        return 130
    except Exception as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
