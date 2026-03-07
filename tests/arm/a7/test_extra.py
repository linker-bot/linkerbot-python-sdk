"""Tests for A7 arm PID setting and zero calibration (interactive).

Only executed when explicitly selected via: -m extra
"""

import pytest

from linkerbot.arm import A7
from tests.arm.a7.conftest import NUM_JOINTS, get_pid_params
from tests.conftest import InteractiveSession

pytestmark = [pytest.mark.a7, pytest.mark.interactive, pytest.mark.extra]


class TestPIDSetting:
    """Test PID parameter read/write/restore cycle (non-destructive)."""

    def test_pid_read_write_restore(self, a7_arm: A7) -> None:
        """Read PID -> modify each value +0.1 -> verify -> restore -> verify."""
        a7_arm.enable()
        try:
            original = get_pid_params(a7_arm)
            print(f"\nOriginal PID parameters: {original}")

            new_loc_kp = [v + 0.1 for v in original["loc_kp"]]
            new_speed_kp = [v + 0.1 for v in original["speed_kp"]]
            new_speed_ki = [v + 0.1 for v in original["speed_ki"]]

            a7_arm.set_position_kps(new_loc_kp)
            a7_arm.set_velocity_kps(new_speed_kp)
            a7_arm.set_velocity_kis(new_speed_ki)

            updated = get_pid_params(a7_arm)
            for key in original:
                for i in range(NUM_JOINTS):
                    expected = original[key][i] + 0.1
                    actual = updated[key][i]
                    assert abs(actual - expected) < 0.01, (
                        f"{key}[{i}]: after set {actual:.4f} != expected {expected:.4f}"
                    )

            a7_arm.set_position_kps(original["loc_kp"])
            a7_arm.set_velocity_kps(original["speed_kp"])
            a7_arm.set_velocity_kis(original["speed_ki"])

            restored = get_pid_params(a7_arm)
            for key in original:
                for i in range(NUM_JOINTS):
                    assert abs(restored[key][i] - original[key][i]) < 0.01, (
                        f"{key}[{i}]: after restore "
                        f"{restored[key][i]:.4f} != original {original[key][i]:.4f}"
                    )

        finally:
            a7_arm.disable()


class TestCalibrateZero:
    """Test zero calibration — WARNING: this permanently changes the arm's zero point."""

    def test_calibrate_zero_flow(
        self, a7_arm: A7, interactive_session: InteractiveSession
    ) -> None:
        """Full zero calibration flow with double confirmation via InteractiveSession."""
        session = interactive_session

        session.step(
            instruction=(
                "WARNING: This test will PERMANENTLY change the arm's zero point! "
                "Confirm to proceed (mark 'y' only if you are sure)"
            ),
            action=lambda: None,
            expected="User has confirmed they want to proceed with zero calibration",
        ).step(
            instruction=(
                "WARNING (second confirmation): zero calibration cannot be undone easily. "
                "Confirm again to proceed"
            ),
            action=lambda: None,
            expected="User has confirmed a second time",
        ).step(
            instruction="Enabling then disabling arm. Manually move arm to zero position",
            action=lambda: (a7_arm.enable(), a7_arm.disable()),
            expected="Arm is disabled and free to be moved to zero position",
        ).step(
            instruction="Calling calibrate_zero()",
            action=lambda: a7_arm.calibrate_zero(),
            expected="Zero calibration command sent without error",
        ).step(
            instruction=(
                "Enabling arm, setting velocity 0.3, "
                "sending HOME to verify new zero point"
            ),
            action=lambda: (
                a7_arm.enable(),
                a7_arm.set_velocities([0.3] * NUM_JOINTS),
                a7_arm.home(blocking=True),
                a7_arm.wait_motion_done(),
            ),
            expected="Arm should be at the newly calibrated zero position",
        )

        test_target = [0.0, 0.3, 0.0, -0.3, 0.0, 0.0, 0.0]
        session.step(
            instruction=f"move_j to {test_target} to verify motion after calibration",
            action=lambda: a7_arm.move_j(test_target, blocking=True),
            expected="Arm should move correctly to target joints",
        ).step(
            instruction="Returning HOME to verify zero position consistency",
            action=lambda: (
                a7_arm.home(blocking=True),
                a7_arm.wait_motion_done(),
            ),
            expected="Arm should return precisely to zero position",
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
