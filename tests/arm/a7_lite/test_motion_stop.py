"""Tests for A7lite arm motion stop and PID display (interactive)."""

import time

import pytest

from linkerbot.arm import A7lite
from tests.arm.a7_lite.conftest import prepare_interactive_test
from tests.conftest import InteractiveSession

pytestmark = [pytest.mark.a7_lite, pytest.mark.interactive, pytest.mark.motion]

NUM_JOINTS = 7


class TestMotionStop:
    """Test non-blocking motion, is_moving detection, and emergency stop."""

    def test_motion_detect_and_emergency_stop(
        self,
        a7_lite_arm: A7lite,
        arm_side: str,
        a7_lite_pid_params: dict[str, list[float]],
        interactive_session: InteractiveSession,
    ):
        """Non-blocking move_j, check is_moving, emergency_stop, then home."""
        session = interactive_session
        errors: list[str] = []

        print("\nCurrent motor PID parameters (from a7_lite_arm fixture):")
        for name, values in a7_lite_pid_params.items():
            print(f"  {name}: {values}")

        session.step(
            instruction=(
                "Preparing: enable -> velocity 0.3 -> HOME. "
                "Please confirm arm is at zero"
            ),
            action=lambda: prepare_interactive_test(a7_lite_arm),
            expected="Arm should be at zero position, enabled",
        )

        def _move_and_check() -> None:
            target = [0.0] * NUM_JOINTS
            if arm_side == "left":
                target[1] = -1.0
            else:
                target[1] = 1.0
            a7_lite_arm.move_j(target, blocking=False)

            time.sleep(0.3)
            moving = a7_lite_arm.is_moving()
            print(f"\nis_moving() at 0.5 s after non-blocking move_j: {moving}")
            if not moving:
                errors.append(
                    "is_moving() returned False 0.5 s after non-blocking move_j"
                )

            time.sleep(0.5)
            a7_lite_arm.emergency_stop()
            print("emergency_stop() sent")

        if arm_side == "left":
            target_angle_str = "- 1.0"
        else:
            target_angle_str = "+ 1.0"
        session.step(
            instruction=(
                f"Non-blocking move_j: joint 2 -> {target_angle_str} rad. "
                "Will check is_moving at 0.5 s, then emergency_stop at 1.0 s"
            ),
            action=_move_and_check,
            expected="Arm should have started moving, then stopped after emergency_stop",
        )

        def _home_after_stop() -> None:
            # emergency_stop() sets velocities to 0 but does NOT reset the
            # motion_timer.  wait_motion_done() must be called before move_j()
            # (invoked inside home()) to satisfy the _guard_not_moving check.
            a7_lite_arm.set_velocities([0.3] * 7)
            a7_lite_arm.wait_motion_done()
            a7_lite_arm.home(blocking=True)

        session.step(
            instruction="Waiting for motion timer, then sending HOME",
            action=_home_after_stop,
            expected="Arm should be back at zero position and enabled",
        )

        session.run()
        session.save_report()

        a7_lite_arm.disable()
        time.sleep(0.1)

        if session.quit_early:
            pytest.exit("Tester quit early")

        failures = session.failed_steps()
        all_errors = [f"- {f.instruction}: {f.notes}" for f in failures]
        all_errors.extend(f"- [auto] {e}" for e in errors)
        if all_errors:
            pytest.fail(
                f"{len(all_errors)} issue(s) detected:\n" + "\n".join(all_errors)
            )
