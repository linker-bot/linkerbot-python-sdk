"""Tests for A7 arm safety verification with hardware (interactive)."""

import time

import pytest

from linkerbot.arm import A7
from tests.conftest import InteractiveSession

pytestmark = [pytest.mark.a7, pytest.mark.interactive, pytest.mark.safety]

NUM_JOINTS = 7
ZERO_TOLERANCE_RAD = 0.08


class TestEnableDisableVerification:
    """Human verifies enable/disable state transitions."""

    def test_enable_disable_states(
        self, a7_arm: A7, interactive_session: InteractiveSession
    ):
        """Verify disable and enable produce observable state changes."""
        session = interactive_session

        session.step(
            instruction="Sending DISABLE command to the arm",
            action=lambda: a7_arm.disable(),
            expected="Arm should be in disabled state (motors free to move by hand)",
        ).step(
            instruction="Sending ENABLE command to the arm",
            action=lambda: a7_arm.enable(),
            expected="Arm should be in enabled state (motors holding position)",
        ).step(
            instruction="Sending DISABLE command again",
            action=lambda: a7_arm.disable(),
            expected="Arm should return to disabled state",
        )

        session.run()
        session.save_report()

        if session.quit_early:
            pytest.exit("Tester quit early")

        failures = session.failed_steps()
        if failures:
            msgs = [f"- {f.instruction}: {f.notes}" for f in failures]
            pytest.fail(f"{len(failures)} step(s) failed:\n" + "\n".join(msgs))


class TestZeroPointVerification:
    """Human manually sets the arm to zero and verifies angle readings."""

    def test_manual_zero_check(
        self, a7_arm: A7, interactive_session: InteractiveSession
    ):
        """Disable arm, user adjusts to zero, verify angles within tolerance."""
        session = interactive_session

        session.step(
            instruction="Sending DISABLE. Manually move the arm to the zero position",
            action=lambda: a7_arm.disable(),
            expected="Arm is disabled and free to move",
        ).step(
            instruction=(
                "Reading joint angles to verify zero position "
                f"(tolerance: {ZERO_TOLERANCE_RAD} rad per joint)"
            ),
            action=lambda: print(
                f"\nCurrent angles: {a7_arm.get_angles()}\n"
                f"All within tolerance: "
                f"{all(abs(a) < ZERO_TOLERANCE_RAD for a in a7_arm.get_angles())}"
            ),
            expected=(
                f"All {NUM_JOINTS} joint angles should be within "
                f"+/-{ZERO_TOLERANCE_RAD} rad of 0"
            ),
        ).step(
            instruction="Enabling arm, setting velocity 0.3, sending HOME command",
            action=lambda: (
                a7_arm.enable(),
                time.sleep(0.2),
                a7_arm.set_velocities([0.3] * NUM_JOINTS),
                time.sleep(0.2),
                a7_arm.home(blocking=True),
                a7_arm.wait_motion_done(),
            ),
            expected="Arm should move to and hold at the zero position",
        )

        session.run()
        session.save_report()

        a7_arm.disable()

        if session.quit_early:
            pytest.exit("Tester quit early")

        failures = session.failed_steps()
        if failures:
            msgs = [f"- {f.instruction}: {f.notes}" for f in failures]
            pytest.fail(f"{len(failures)} step(s) failed:\n" + "\n".join(msgs))


class TestJointDirectionVerification:
    """Verify positive direction of each joint matches URDF definition."""

    def test_all_joint_directions(
        self,
        a7_arm: A7,
        arm_side: str,
        interactive_session: InteractiveSession,
    ):
        """Move each joint +0.2 rad and verify direction matches URDF."""
        session = interactive_session

        session.step(
            instruction="Enabling arm, setting velocity 0.3, sending HOME",
            action=lambda: (
                a7_arm.enable(),
                a7_arm.set_velocities([0.3] * NUM_JOINTS),
                a7_arm.home(blocking=True),
                a7_arm.wait_motion_done(),
            ),
            expected="Arm should be at zero position, enabled",
        )

        for i in range(NUM_JOINTS):
            if i == 1:
                if arm_side == "left":
                    target_pos = [0.0, 0.2, 0.0, 0.0, 0.0, 0.0, 0.0]
                else:
                    target_pos = [0.0, -0.2, 0.0, 0.0, 0.0, 0.0, 0.0]
            else:
                target_pos = [0.0] * NUM_JOINTS
                target_pos[i] = 0.2

            # if i == 3:
            #     target_pos[i] = -0.2

            target_direction = (
                "NEGATIVE"
                # if (i == 3) or (i == 1 and arm_side == "right")
                if (i == 1 and arm_side == "right")
                else "POSITIVE"
            )
            target_angle_str = (
                # "- 0.2" if (i == 3) or (i == 1 and arm_side == "right") else "+ 0.2"
                "- 0.2" if (i == 1 and arm_side == "right") else "+ 0.2"
            )

            session.step(
                instruction=(
                    f"Joint {i + 1}: moving to {target_angle_str} rad (target: {target_pos})"
                ),
                action=lambda t=target_pos: (
                    a7_arm.move_j(t, blocking=True),
                    a7_arm.wait_motion_done(),
                    time.sleep(2),
                    a7_arm.home(blocking=True),
                    a7_arm.wait_motion_done(),
                ),
                expected=(
                    f"Joint {i + 1} should move in the {target_direction} direction "
                    "matching URDF definition"
                ),
            )

        session.run()
        session.save_report()

        a7_arm.disable()

        if session.quit_early:
            pytest.exit("Tester quit early")

        failures = session.failed_steps()
        if failures:
            msgs = [f"- {f.instruction}: {f.notes}" for f in failures]
            pytest.fail(f"{len(failures)} step(s) failed:\n" + "\n".join(msgs))
