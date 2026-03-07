"""Tests for A7lite arm complex motion with hardware (interactive).

Covers:
  Section 1 — move_j at 3 velocity/acceleration profiles
  Section 2 — move_p / move_l in Maestro frame (default / high / low speed)
  Section 3 — Maestro <-> URDF coordinate consistency verification
  Section 4 — move_p / move_l in URDF frame
"""

import os
import time
from typing import Literal, cast

import pytest

from linkerbot.arm import A7lite, Pose
from tests.conftest import InteractiveSession

pytestmark = [pytest.mark.a7_lite, pytest.mark.interactive, pytest.mark.motion]

NUM_JOINTS = 7
POS_TOLERANCE = 0.01  # 1 cm

# ---------------------------------------------------------------------------
# Section 1 — move_j data
# ---------------------------------------------------------------------------

MOVE_J_TARGETS: dict[str, list[tuple[str, list[float]]]] = {
    "left": [
        ("Elbow raise", [0.0, 0.0, 0.0, 1.57, 0.0, 0.0, 0.0]),
        ("Side swing", [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]),
    ],
    "right": [
        ("Elbow raise", [0.0, 0.0, 0.0, -1.57, 0.0, 0.0, 0.0]),
        ("Side swing", [-1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]),
    ],
}

MOVE_J_PROFILES: list[tuple[str, float, float]] = [
    # (label, velocity rad/s, acceleration rad/s²)
    ("Low vel / Low acc", 0.5, 1.0),
    ("High vel / Low acc", 10.0, 1.0),
    ("High vel / High acc", 10.0, 10.0),
]

# ---------------------------------------------------------------------------
# Section 2 — Cartesian (Maestro frame) data
# ---------------------------------------------------------------------------

MAESTRO_INIT_POSE: dict[str, list[float]] = {
    "left": [0.0, 0.33, -0.25, 1.85, 0.0, -1.57],
    "right": [0.0, 0.33, -0.25, 1.85, 0.0, 1.57],
}
CARTESIAN_CASES_DEFAULT: list[tuple[str, list[float]]] = [
    ("Pure Z +5 cm", [0.0, 0.0, 0.05, 0.0, 0.0, 0.0]),
    ("Pure X +10 cm", [0.10, 0.0, 0.0, 0.0, 0.0, 0.0]),
    ("XZ diagonal +5 cm", [0.05, 0.0, 0.05, 0.0, 0.0, 0.0]),
    ("Short X +1 mm", [0.001, 0.0, 0.0, 0.0, 0.0, 0.0]),
    ("Pure rx +0.2 rad", [0.0, 0.0, 0.0, 0.2, 0.0, 0.0]),
    ("Pure rz +0.3 rad", [0.0, 0.0, 0.0, 0.0, 0.0, 0.3]),
    ("Z +5 cm + rx +0.2", [0.0, 0.0, 0.05, 0.2, 0.0, 0.0]),
    ("Mixed all axes", [0.08, 0.08, 0.08, 0.15, 0.1, 0.15]),
    ("XZ +5 cm + rz +0.3", [0.05, 0.0, 0.05, 0.0, 0.0, 0.3]),
]

CARTESIAN_CASES_HIGH: list[tuple[str, list[float]]] = [
    ("High-speed X +10 cm", [0.10, 0.0, 0.0, 0.0, 0.0, 0.0]),
    ("High-speed mixed", [0.10, 0.0, 0.05, 0.3, 0.0, 0.0]),
]

CARTESIAN_CASES_LOW: list[tuple[str, list[float]]] = [
    ("Low-speed X +10 cm", [0.10, 0.0, 0.0, 0.0, 0.0, 0.0]),
    ("Low-speed mixed", [0.10, 0.0, 0.05, 0.3, 0.0, 0.0]),
]

# Joint-level velocity/acceleration profiles for move_p
MOVE_P_VEL_ACC: dict[str, tuple[float, float]] = {
    "default": (1.0, 10.0),  # (velocity rad/s, acceleration rad/s²)
    "high": (5.0, 50.0),  # 5x default
    "low": (0.2, 2.0),  # 1/5 default
}

# Cartesian speed profiles for move_l
MOVE_L_PARAMS: dict[str, dict[str, float]] = {
    "default": {
        "max_velocity": 0.05,
        "acceleration": 0.1,
        "max_angular_velocity": 0.3,
        "angular_acceleration": 0.4,
    },
    "high": {  # 5x default
        "max_velocity": 0.25,
        "acceleration": 0.5,
        "max_angular_velocity": 1.5,
        "angular_acceleration": 1.0,
    },
    "low": {  # 1/5 default
        "max_velocity": 0.01,
        "acceleration": 0.02,
        "max_angular_velocity": 0.06,
        "angular_acceleration": 0.1,
    },
}

# ---------------------------------------------------------------------------
# Section 3 — Maestro <-> URDF consistency data
# ---------------------------------------------------------------------------

MAESTRO_URDF_OFFSET: dict[str, list[float]] = {
    "left": [0.03125, 0.215, 0.0],
    "right": [0.03125, -0.215, 0.0],
}

CONSISTENCY_PAIRS: dict[str, list[dict[str, list[float]]]] = {
    "left": [
        {
            "maestro": [0.0, 0.33, -0.25, 1.5, 0.0, -1.57],
            "urdf": [0.36125, 0.215, -0.25, 0.0, -1.5, -1.57],
        },
        {
            "maestro": [0.0, 0.33, -0.25, 1.5, 0.0, 0.0],
            "urdf": [0.36125, 0.215, -0.25, 0.0, -1.5, 0.0],
        },
    ],
    "right": [
        {
            "maestro": [0.0, 0.33, -0.25, 1.5, 0.0, 1.57],
            "urdf": [0.36125, -0.215, -0.25, 0.0, -1.5, -1.57],
        },
        {
            "maestro": [0.0, 0.33, -0.25, 1.5, 0.0, 0.0],
            "urdf": [0.36125, -0.215, -0.25, 0.0, -1.5, 0.0],
        },
    ],
}

# ---------------------------------------------------------------------------
# Section 4 — URDF frame initial poses
# ---------------------------------------------------------------------------

URDF_INIT_POSE: dict[str, list[float]] = {
    "left": [0.36125, 0.215, -0.25, 0.0, -1.5, -1.57],
    "right": [0.36125, -0.215, -0.25, 0.0, -1.5, 1.57],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _apply_offset(base: list[float], offset: list[float]) -> Pose:
    """Add offset to base pose element-wise and return a Pose."""
    return Pose.from_list([b + o for b, o in zip(base, offset)])


def _maestro_pos_to_urdf(mx: float, my: float, mz: float, side: str) -> list[float]:
    """Convert Maestro XYZ to URDF XYZ.

    Formula (position only):
      left:  urdf = [m_y, -m_x, m_z] + [0.03125,  0.215, 0]
      right: urdf = [m_y, -m_x, m_z] + [0.03125, -0.215, 0]
    """
    off = MAESTRO_URDF_OFFSET[side]
    return [my + off[0], -mx + off[1], mz + off[2]]


def _run_session(session: InteractiveSession) -> None:
    """Execute session, save report, and fail on any human-marked or logic issues."""
    session.run()
    session.save_report()

    if session.quit_early:
        pytest.exit("Tester quit early")

    failures = session.failed_steps()
    if failures:
        msgs = [f"- {f.instruction}: {f.notes}" for f in failures]
        pytest.fail(f"{len(failures)} step(s) failed:\n" + "\n".join(msgs))


# ===================================================================
# Section 1 — move_j basic motion test
# ===================================================================


class TestMoveJBasic:
    """Verify joint-space motion at 3 velocity/acceleration profiles."""

    def test_move_j_profiles(
        self,
        a7_lite_arm: A7lite,
        arm_side: str,
        interactive_session: InteractiveSession,
    ) -> None:
        """Run elbow-raise and side-swing at low/high vel and high acc profiles."""
        session = interactive_session
        targets = MOVE_J_TARGETS[arm_side]

        session.step(
            instruction="Enabling arm, sending HOME",
            action=lambda: (a7_lite_arm.enable(), a7_lite_arm.home(blocking=True)),
            expected="Arm should be at zero position, enabled",
        )

        for prof_label, vel, acc in MOVE_J_PROFILES:
            session.step(
                instruction=(
                    f"Setting profile: {prof_label} (vel={vel} rad/s, acc={acc} rad/s²)"
                ),
                action=lambda v=vel, a=acc: (
                    a7_lite_arm.set_velocities([v] * NUM_JOINTS),
                    a7_lite_arm.set_accelerations([a] * NUM_JOINTS),
                    time.sleep(0.5),
                ),
                expected=f"Velocity={vel} rad/s, acceleration={acc} rad/s² applied",
            )

            for tgt_label, joints in targets:
                session.step(
                    instruction=f"[{prof_label}] {tgt_label}: move_j {joints}",
                    action=lambda j=joints: a7_lite_arm.move_j(j, blocking=True),
                    expected=f"Arm should reach target smoothly ({prof_label})",
                ).step(
                    instruction=f"[{prof_label}] {tgt_label}: returning HOME",
                    action=lambda: a7_lite_arm.home(blocking=True),
                    expected="Arm should be back at zero",
                )

        session.step(
            instruction="Returning HOME, then disable",
            action=lambda: (
                a7_lite_arm.home(blocking=True),
                a7_lite_arm.disable(),
                time.sleep(1.0),
            ),
            expected="Arm at zero, disabled and stationary",
        )

        _run_session(session)


# ===================================================================
# Section 2 — Maestro-frame move_p / move_l
# ===================================================================


class TestMovePMaestro:
    """Verify move_p in Maestro frame at default / high / low speed."""

    def test_move_p_maestro_frame(
        self,
        a7_lite_arm: A7lite,
        arm_side: str,
        interactive_session: InteractiveSession,
    ) -> None:
        """13 offset cases: default (1-9), high-speed (10-11), low-speed (12-13)."""
        session = interactive_session
        init_pose = MAESTRO_INIT_POSE[arm_side]
        init_pose_obj = Pose.from_list(init_pose)

        def _prepare() -> None:
            a7_lite_arm.enable()
            v, a = MOVE_P_VEL_ACC["default"]
            a7_lite_arm.set_velocities([v] * NUM_JOINTS)
            a7_lite_arm.set_accelerations([a] * NUM_JOINTS)
            time.sleep(0.5)

        session.step(
            instruction="Enabling arm, setting default vel/acc (1.0 / 10.0), wait 0.5 s",
            action=_prepare,
            expected="Arm enabled with vel=1.0 rad/s, acc=10.0 rad/s²",
        ).step(
            instruction=f"move_p to initial pose {init_pose}",
            action=lambda: a7_lite_arm.move_p(init_pose_obj, blocking=True),
            expected="Arm TCP at Maestro initial pose",
        )

        # --- Default speed: cases 1-9 ---
        for idx, (label, offset) in enumerate(CARTESIAN_CASES_DEFAULT, 1):
            target = _apply_offset(init_pose, offset)
            session.step(
                instruction=f"[DEFAULT #{idx}] {label}: move_p to {target.to_list()}",
                action=lambda t=target: a7_lite_arm.move_p(t, blocking=True),
                expected=f"TCP should reach target ({label})",
            ).step(
                instruction=f"[DEFAULT #{idx}] Returning to initial pose",
                action=lambda: a7_lite_arm.move_p(init_pose_obj, blocking=True),
                expected="TCP back at initial pose",
            )

        # --- High speed: cases 10-11 ---
        def _set_high() -> None:
            v, a = MOVE_P_VEL_ACC["high"]
            a7_lite_arm.set_velocities([v] * NUM_JOINTS)
            a7_lite_arm.set_accelerations([a] * NUM_JOINTS)
            time.sleep(0.5)

        session.step(
            instruction="Setting HIGH speed (5x default: vel=5.0, acc=50.0), wait 0.5 s",
            action=_set_high,
            expected="High speed profile applied",
        )

        for idx, (label, offset) in enumerate(CARTESIAN_CASES_HIGH, 10):
            target = _apply_offset(init_pose, offset)
            session.step(
                instruction=f"[HIGH #{idx}] {label}: move_p to {target.to_list()}",
                action=lambda t=target: a7_lite_arm.move_p(t, blocking=True),
                expected=f"TCP should reach target at high speed ({label})",
            ).step(
                instruction=f"[HIGH #{idx}] Returning to initial pose",
                action=lambda: a7_lite_arm.move_p(init_pose_obj, blocking=True),
                expected="TCP back at initial pose",
            )

        # --- Low speed: cases 12-13 ---
        def _set_low() -> None:
            v, a = MOVE_P_VEL_ACC["low"]
            a7_lite_arm.set_velocities([v] * NUM_JOINTS)
            a7_lite_arm.set_accelerations([a] * NUM_JOINTS)
            time.sleep(0.5)

        session.step(
            instruction="Setting LOW speed (1/5 default: vel=0.2, acc=2.0), wait 0.5 s",
            action=_set_low,
            expected="Low speed profile applied",
        )

        for idx, (label, offset) in enumerate(CARTESIAN_CASES_LOW, 12):
            target = _apply_offset(init_pose, offset)
            session.step(
                instruction=f"[LOW #{idx}] {label}: move_p to {target.to_list()}",
                action=lambda t=target: a7_lite_arm.move_p(t, blocking=True),
                expected=f"TCP should reach target at low speed ({label})",
            ).step(
                instruction=f"[LOW #{idx}] Returning to initial pose",
                action=lambda: a7_lite_arm.move_p(init_pose_obj, blocking=True),
                expected="TCP back at initial pose",
            )

        session.step(
            instruction="Returning HOME, then disable",
            action=lambda: (a7_lite_arm.home(blocking=True), a7_lite_arm.disable()),
            expected="Arm at zero, disabled",
        )

        _run_session(session)


class TestMoveLMaestro:
    """Verify move_l in Maestro frame at default / high / low speed.

    Same 13 cases as TestMovePMaestro, using move_l (straight-line Cartesian path).
    """

    def test_move_l_maestro_frame(
        self,
        a7_lite_arm: A7lite,
        arm_side: str,
        interactive_session: InteractiveSession,
    ) -> None:
        """13 offset cases: default (1-9), high-speed (10-11), low-speed (12-13)."""
        session = interactive_session
        init_pose = MAESTRO_INIT_POSE[arm_side]
        init_pose_obj = Pose.from_list(init_pose)

        def _prepare() -> None:
            a7_lite_arm.enable()
            v, a = MOVE_P_VEL_ACC["default"]
            a7_lite_arm.set_velocities([v] * NUM_JOINTS)
            a7_lite_arm.set_accelerations([a] * NUM_JOINTS)
            time.sleep(0.5)

        session.step(
            instruction="Enabling arm, setting default vel/acc (1.0 / 10.0), wait 0.5 s",
            action=_prepare,
            expected="Arm enabled with vel=1.0 rad/s, acc=10.0 rad/s²",
        ).step(
            instruction=f"move_p to initial pose {init_pose} (use move_p to reach start)",
            action=lambda: a7_lite_arm.move_p(init_pose_obj, blocking=True),
            expected="Arm TCP at Maestro initial pose",
        )

        default_params = MOVE_L_PARAMS["default"]

        # --- Default speed: cases 1-9 ---
        for idx, (label, offset) in enumerate(CARTESIAN_CASES_DEFAULT, 1):
            target = _apply_offset(init_pose, offset)
            session.step(
                instruction=f"[DEFAULT #{idx}] {label}: move_l to {target.to_list()}",
                action=lambda t=target, p=default_params: a7_lite_arm.move_l(t, **p),
                expected=f"TCP should reach target in a straight line ({label})",
            ).step(
                instruction=f"[DEFAULT #{idx}] Returning to initial pose via move_l",
                action=lambda p=default_params: a7_lite_arm.move_l(init_pose_obj, **p),
                expected="TCP back at initial pose",
            )

        # --- High speed: cases 10-11 ---
        high_params = MOVE_L_PARAMS["high"]
        session.step(
            instruction=f"Switching to HIGH speed move_l params (5x default): {high_params}",
            action=lambda: None,
            expected="Acknowledged — subsequent move_l will use high speed",
        )

        for idx, (label, offset) in enumerate(CARTESIAN_CASES_HIGH, 10):
            target = _apply_offset(init_pose, offset)
            session.step(
                instruction=f"[HIGH #{idx}] {label}: move_l to {target.to_list()}",
                action=lambda t=target, p=high_params: a7_lite_arm.move_l(t, **p),
                expected=f"TCP should reach target at high speed ({label})",
            ).step(
                instruction=f"[HIGH #{idx}] Returning to initial pose via move_l",
                action=lambda p=high_params: a7_lite_arm.move_l(init_pose_obj, **p),
                expected="TCP back at initial pose",
            )

        # --- Low speed: cases 12-13 ---
        low_params = MOVE_L_PARAMS["low"]
        session.step(
            instruction=f"Switching to LOW speed move_l params (1/5 default): {low_params}",
            action=lambda: None,
            expected="Acknowledged — subsequent move_l will use low speed",
        )

        for idx, (label, offset) in enumerate(CARTESIAN_CASES_LOW, 12):
            target = _apply_offset(init_pose, offset)
            session.step(
                instruction=f"[LOW #{idx}] {label}: move_l to {target.to_list()}",
                action=lambda t=target, p=low_params: a7_lite_arm.move_l(t, **p),
                expected=f"TCP should reach target at low speed ({label})",
            ).step(
                instruction=f"[LOW #{idx}] Returning to initial pose via move_l",
                action=lambda p=low_params: a7_lite_arm.move_l(init_pose_obj, **p),
                expected="TCP back at initial pose",
            )

        session.step(
            instruction="Returning HOME, then disable",
            action=lambda: (a7_lite_arm.home(blocking=True), a7_lite_arm.disable()),
            expected="Arm at zero, disabled",
        )

        _run_session(session)


# ===================================================================
# Section 3 — Maestro <-> URDF coordinate consistency verification
# ===================================================================


class TestCoordinateConsistency:
    """Verify Maestro -> URDF position conversion and forward-kinematics consistency.

    Position conversion formula (applied to the TCP position reported by get_pose()):
      left:  urdf_xyz = [m_y + 0.03125,  -m_x + 0.215,  m_z]
      right: urdf_xyz = [m_y + 0.03125,  -m_x - 0.215,  m_z]

    Orientation conversion is NOT a simple Euler-angle addition; expected URDF
    orientations are taken from the pre-computed lookup table CONSISTENCY_PAIRS.
    """

    def test_maestro_urdf_consistency(
        self,
        a7_lite_arm: A7lite,
        arm_side: str,
        interactive_session: InteractiveSession,
    ) -> None:
        """Move to each Maestro pose, verify converted URDF position matches table."""
        session = interactive_session
        pairs = CONSISTENCY_PAIRS[arm_side]

        session.step(
            instruction="Enabling arm, setting vel=1.0 / acc=10.0, HOME",
            action=lambda: (
                a7_lite_arm.enable(),
                a7_lite_arm.set_velocities([1.0] * NUM_JOINTS),
                a7_lite_arm.set_accelerations([10.0] * NUM_JOINTS),
                time.sleep(0.5),
                a7_lite_arm.home(blocking=True),
            ),
            expected="Arm at zero position, enabled",
        )

        for pair_idx, pair in enumerate(pairs):
            maestro_pose = pair["maestro"]
            expected_urdf = pair["urdf"]
            target_obj = Pose.from_list(maestro_pose)

            def _move_and_verify(
                mp: list[float] = maestro_pose,
                eu: list[float] = expected_urdf,
                t: Pose = target_obj,
            ) -> None:
                a7_lite_arm.move_p(t, blocking=True)

                actual = a7_lite_arm.get_pose().to_list()
                print(f"\nMaestro pose reported:   {actual}")
                print(f"Maestro pose expected:   {mp}")

                converted_urdf_pos = _maestro_pos_to_urdf(
                    actual[0], actual[1], actual[2], arm_side
                )
                print(f"Converted URDF XYZ:      {converted_urdf_pos}")
                print(f"Expected URDF XYZ:       {eu[:3]}")

                for axis, (got, exp) in enumerate(zip(converted_urdf_pos, eu[:3])):
                    assert abs(got - exp) < POS_TOLERANCE, (
                        f"Pair {pair_idx + 1} URDF axis {axis}: "
                        f"got {got:.4f} m, expected {exp:.4f} m "
                        f"(tol={POS_TOLERANCE} m)"
                    )

            session.step(
                instruction=(
                    f"[Pair {pair_idx + 1}] move_p to Maestro {maestro_pose}, "
                    f"verify URDF position -> {expected_urdf[:3]}"
                ),
                action=_move_and_verify,
                expected=(
                    f"Converted URDF XYZ within {POS_TOLERANCE} m of expected "
                    f"{expected_urdf[:3]}"
                ),
            )

            if pair_idx < len(pairs) - 1:
                session.step(
                    instruction="Waiting 4 s before next pose",
                    action=lambda: time.sleep(4.0),
                    expected="4 s elapsed",
                )

        session.step(
            instruction="Returning HOME, then disable",
            action=lambda: (a7_lite_arm.home(blocking=True), a7_lite_arm.disable()),
            expected="Arm at zero, disabled",
        )

        _run_session(session)


# ===================================================================
# Section 4 — URDF-frame move_p / move_l
#
# These tests create a separate A7lite instance with world_frame="urdf".
# Run them separately from the Maestro-frame tests to avoid having two
# instances of A7lite send commands to the same CAN bus simultaneously:
#   pytest tests/arm/a7_lite/test_complex_motion.py -k TestCartesianURDF
# ===================================================================


class TestCartesianURDF:
    """Verify move_p and move_l in URDF coordinate frame.

    Creates its own A7lite instance with world_frame='urdf' and manages
    the full lifecycle internally via try/finally.
    """

    @staticmethod
    def _create_urdf_arm(side: str) -> A7lite:
        interface = os.environ.get("CAN_INTERFACE", "can0")
        return A7lite(
            side=cast(Literal["left", "right"], side),
            interface_name=interface,
            world_frame="urdf",
        )

    def test_move_p_urdf_frame(
        self,
        arm_side: str,
        interactive_session: InteractiveSession,
    ) -> None:
        """move_p in URDF frame — 9 default-speed offset cases."""
        session = interactive_session
        init_pose = URDF_INIT_POSE[arm_side]
        init_pose_obj = Pose.from_list(init_pose)

        arm = self._create_urdf_arm(arm_side)
        try:

            def _prepare() -> None:
                arm.enable()
                v, a = MOVE_P_VEL_ACC["default"]
                arm.set_velocities([v] * NUM_JOINTS)
                arm.set_accelerations([a] * NUM_JOINTS)
                time.sleep(0.5)

            session.step(
                instruction="[URDF] Enabling arm (world_frame=urdf), vel=1.0 / acc=10.0",
                action=_prepare,
                expected="Arm enabled in URDF frame",
            ).step(
                instruction=f"[URDF] move_p to URDF initial pose {init_pose}",
                action=lambda: arm.move_p(init_pose_obj, blocking=True),
                expected="Arm TCP at URDF initial pose",
            )

            for idx, (label, offset) in enumerate(CARTESIAN_CASES_DEFAULT, 1):
                target = _apply_offset(init_pose, offset)
                session.step(
                    instruction=(
                        f"[URDF move_p #{idx}] {label}: target={target.to_list()}"
                    ),
                    action=lambda t=target: arm.move_p(t, blocking=True),
                    expected=f"TCP should reach target ({label})",
                ).step(
                    instruction=f"[URDF move_p #{idx}] Returning to init pose",
                    action=lambda: arm.move_p(init_pose_obj, blocking=True),
                    expected="TCP back at URDF init pose",
                )

            session.step(
                instruction="[URDF] Returning HOME, then disable",
                action=lambda: (arm.home(blocking=True), arm.disable()),
                expected="Arm at zero, disabled",
            )

            _run_session(session)

        finally:
            arm.close()

    def test_move_l_urdf_frame(
        self,
        arm_side: str,
        interactive_session: InteractiveSession,
    ) -> None:
        """move_l in URDF frame — 9 default-speed offset cases."""
        session = interactive_session
        init_pose = URDF_INIT_POSE[arm_side]
        init_pose_obj = Pose.from_list(init_pose)
        default_params = MOVE_L_PARAMS["default"]

        arm = self._create_urdf_arm(arm_side)
        try:

            def _prepare() -> None:
                arm.enable()
                v, a = MOVE_P_VEL_ACC["default"]
                arm.set_velocities([v] * NUM_JOINTS)
                arm.set_accelerations([a] * NUM_JOINTS)
                time.sleep(0.5)

            session.step(
                instruction="[URDF] Enabling arm (world_frame=urdf), vel=1.0 / acc=10.0",
                action=_prepare,
                expected="Arm enabled in URDF frame",
            ).step(
                instruction=f"[URDF] move_p to URDF initial pose {init_pose} (use move_p to reach start)",
                action=lambda: arm.move_p(init_pose_obj, blocking=True),
                expected="Arm TCP at URDF initial pose",
            )

            for idx, (label, offset) in enumerate(CARTESIAN_CASES_DEFAULT, 1):
                target = _apply_offset(init_pose, offset)
                session.step(
                    instruction=(
                        f"[URDF move_l #{idx}] {label}: target={target.to_list()}"
                    ),
                    action=lambda t=target, p=default_params: arm.move_l(t, **p),
                    expected=f"TCP straight-line to target ({label})",
                ).step(
                    instruction=f"[URDF move_l #{idx}] Returning to init pose",
                    action=lambda p=default_params: arm.move_l(init_pose_obj, **p),
                    expected="TCP back at URDF init pose",
                )

            session.step(
                instruction="[URDF] Returning HOME, then disable",
                action=lambda: (arm.home(blocking=True), arm.disable()),
                expected="Arm at zero, disabled",
            )

            _run_session(session)

        finally:
            arm.close()
