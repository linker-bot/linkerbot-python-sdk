"""Tests for A7 arm basic functionality with hardware."""

import time

import pytest

from linkerbot.arm import A7

pytestmark = [pytest.mark.a7, pytest.mark.basic]

NUM_JOINTS = 7

PARAMETERS_NAMES = [
    "joint_angles",
    "joint_control_angles",
    "joint_velocities",
    "joint_control_velocities",
    "joint_control_acceleration",
    "joint_torques",
    "joint_temperatures",
]

UPDATED_PARAMETERS_NAMES = [
    "joint_angles",
    "joint_velocities",
    "joint_torques",
    "joint_temperatures",
]


class TestReadArmState:
    """Test Arm State Reading."""

    def test_read_arm_state_read(self, a7_arm: A7):
        arm_state = a7_arm.get_state()
        assert arm_state is not None, "Arm state is None"
        for parameter_name in PARAMETERS_NAMES:
            parameter = getattr(arm_state, parameter_name)
            assert parameter is not None, f"Arm state {parameter_name} is None"
            assert len(parameter) == NUM_JOINTS, (
                f"Arm state {parameter_name} length is not {NUM_JOINTS}"
            )

    def test_read_arm_state_update(self, a7_arm: A7):
        """Test reading arm state."""
        arm_state = a7_arm.get_state()
        time.sleep(1.5)
        arm_state_updated = a7_arm.get_state()
        for parameter_name in UPDATED_PARAMETERS_NAMES:
            parameter = getattr(arm_state, parameter_name)
            parameter_updated = getattr(arm_state_updated, parameter_name)
            for i in range(NUM_JOINTS):
                assert parameter[i].timestamp < parameter_updated[i].timestamp, (
                    f"Arm state {parameter_name} timestamp is not updated"
                )
