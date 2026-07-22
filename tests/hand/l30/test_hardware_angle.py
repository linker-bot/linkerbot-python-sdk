from __future__ import annotations

import pytest

from tests.hand.l30.hardware_helpers import (
    assert_joint_tuple,
    hardware_settings,
    open_l30,
    require_full_hardware,
    require_motion_allowed,
    safe_angles_from_env,
)

pytestmark = [
    pytest.mark.l30,
    pytest.mark.canfd,
    pytest.mark.hardware,
    pytest.mark.interactive,
]


def test_l30_hardware_angle_read_and_snapshot() -> None:
    require_full_hardware()
    settings = hardware_settings()

    with open_l30() as hand:
        angle = hand.angle.get_blocking(timeout_ms=settings.timeout_ms)
        snapshot = hand.angle.get_snapshot()

    assert_joint_tuple(tuple(angle.angles.to_raw()))
    assert snapshot is angle


def test_l30_hardware_angle_set_safe_pose_from_env() -> None:
    require_full_hardware()
    safe_angles = safe_angles_from_env()
    if safe_angles is None:
        pytest.skip("Set L30_SAFE_ANGLES to run the safe angle movement test")
    require_motion_allowed()

    with open_l30() as hand:
        hand.angle.set_angles(safe_angles)
