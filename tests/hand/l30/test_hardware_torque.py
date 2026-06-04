from __future__ import annotations

import pytest

from tests.hand.l30.hardware_helpers import (
    assert_joint_tuple,
    open_l30,
    require_full_hardware,
    require_motion_allowed,
    safe_torque,
)

pytestmark = [
    pytest.mark.l30,
    pytest.mark.canfd,
    pytest.mark.hardware,
    pytest.mark.interactive,
]


def test_l30_hardware_torque_set_all_safe_value_updates_snapshot() -> None:
    require_full_hardware()
    require_motion_allowed()
    torque = safe_torque()

    with open_l30() as hand:
        hand.torque.set_all(torque)
        snapshot = hand.torque.get_snapshot()

    assert snapshot is not None
    assert_joint_tuple(snapshot.torques)
    assert snapshot.torques == (torque,) * 17
