from __future__ import annotations

import pytest

from linkerbot.hand.l30 import Finger
from tests.hand.l30.hardware_helpers import (
    force_all_fingers_enabled,
    hardware_settings,
    open_l30,
    require_full_hardware,
)

pytestmark = [
    pytest.mark.l30,
    pytest.mark.canfd,
    pytest.mark.hardware,
    pytest.mark.interactive,
]


def test_l30_hardware_force_sensor_single_finger() -> None:
    require_full_hardware()
    settings = hardware_settings()

    with open_l30() as hand:
        force = hand.force_sensor.get_finger(
            Finger.INDEX, timeout_ms=settings.timeout_ms
        )

    assert force.finger is Finger.INDEX
    assert force.values.shape == (12, 6)


def test_l30_hardware_force_sensor_all_fingers_snapshot() -> None:
    require_full_hardware()
    if not force_all_fingers_enabled():
        pytest.skip("Set L30_FORCE_ALL_FINGERS=1 to read all tactile fingers")
    settings = hardware_settings()

    with open_l30() as hand:
        force = hand.force_sensor.get_blocking(timeout_ms=settings.timeout_ms)
        snapshot = hand.force_sensor.get_snapshot()

    assert force.thumb.shape == (12, 6)
    assert force.index.shape == (12, 6)
    assert force.middle.shape == (12, 6)
    assert force.ring.shape == (12, 6)
    assert force.pinky.shape == (12, 6)
    assert snapshot is force
