from __future__ import annotations

import pytest

from linkerbot.hand.l30 import SensorSource
from tests.hand.l30.hardware_helpers import (
    assert_joint_tuple,
    hardware_settings,
    open_l30,
    poll_interval_s,
    require_full_hardware,
    wait_for_angle_snapshot,
)

pytestmark = [
    pytest.mark.l30,
    pytest.mark.canfd,
    pytest.mark.hardware,
    pytest.mark.interactive,
]


def test_l30_hardware_angle_polling_updates_snapshot() -> None:
    require_full_hardware()
    settings = hardware_settings()

    with open_l30() as hand:
        try:
            hand.start_polling({SensorSource.ANGLE: poll_interval_s()})
            angle = wait_for_angle_snapshot(hand, settings.timeout_ms)
        finally:
            hand.stop_polling()

    assert_joint_tuple(tuple(angle.angles.to_raw()))
