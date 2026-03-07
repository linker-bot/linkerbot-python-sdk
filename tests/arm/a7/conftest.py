"""Fixtures for A7 robotic arm tests."""

import os
import time
from typing import Literal, cast

import pytest

from linkerbot.arm import A7

NUM_JOINTS = 7

# Desired run order for a7 test modules (lower = earlier).
A7_TEST_ORDER: dict[str, int] = {
    "test_lifecycle": 1,
    "test_basic": 2,
    "test_safety": 3,
    "test_motion_stop": 4,
    "test_complex_motion": 5,
    "test_extra": 6,
}


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Reorder a7 tests: lifecycle -> basic -> safety -> motion -> complex -> extra."""
    # Build (item, sort_key) preserving original index for non-a7
    indexed: list[tuple[pytest.Item, tuple[int, int, int]]] = []
    for idx, item in enumerate(items):
        path_str = str(item.path)
        if "arm/a7" not in path_str or "conftest" in path_str:
            indexed.append((item, (0, idx, 0)))  # Non-a7: keep original order
        else:
            stem = item.path.stem
            rank = A7_TEST_ORDER.get(stem)
            if rank is not None:
                indexed.append((item, (1, rank, 0)))  # A7: in rank order
            else:
                indexed.append((item, (0, idx, 0)))

    indexed.sort(key=lambda x: x[1])
    items[:] = [i for i, _ in indexed]


@pytest.fixture(scope="module")
def a7_arm():
    """Create A7 arm instance for the test module.

    Uses environment variables for configuration:
    - CAN_INTERFACE: CAN interface name (default: "can0")
    - ARM_SIDE: Arm side, "left" or "right" (default: "left")
    """
    interface = os.environ.get("CAN_INTERFACE", "can0")
    side = cast(Literal["left", "right"], os.environ.get("ARM_SIDE", "left"))

    arm = A7(side=side, interface_name=interface, world_frame="maestro")
    try:
        yield arm
    finally:
        arm.disable()
        arm.close()


@pytest.fixture(scope="module")
def arm_side() -> Literal["left", "right"]:
    """Return configured arm side from ARM_SIDE env var."""
    return cast(Literal["left", "right"], os.environ.get("ARM_SIDE", "left"))


@pytest.fixture(scope="module")
def a7_pid_params(a7_arm: A7) -> dict[str, list[float]]:
    """PID parameters read from the a7_arm fixture instance."""
    return get_pid_params(a7_arm)


def require_input(prompt: str, valid: set[str]) -> str:
    """Require valid user input; empty Enter is rejected, loops until valid."""
    while True:
        answer = input(prompt).strip().lower()
        if answer in valid:
            return answer
        print(f"Invalid input, please enter: {'/'.join(sorted(valid))}")


def prepare_interactive_test(arm: A7) -> None:
    """Common interactive test preparation: confirm -> enable -> low speed -> home -> verify."""
    ans = require_input(
        "Ready to start test? Arm should be disabled, will re-enable (y/n): ",
        {"y", "n"},
    )
    if ans == "n":
        pytest.skip("User cancelled test")

    arm.enable()
    time.sleep(0.2)
    arm.set_velocities([0.3] * NUM_JOINTS)
    time.sleep(0.2)
    arm.home(blocking=True)
    arm.wait_motion_done()

    ans = require_input("Is the arm at the zero position? (y/n): ", {"y", "n"})
    if ans == "n":
        arm.disable()
        pytest.fail("Failed to return to zero position")


def get_pid_params(arm: A7) -> dict[str, list[float]]:
    """Read current PID parameters from all motors."""
    return {
        "loc_kp": [m.velocity_ki for m in arm._motors],
        "speed_kp": [m.velocity_kp for m in arm._motors],
        "speed_ki": [m.velocity_ki for m in arm._motors],
    }
