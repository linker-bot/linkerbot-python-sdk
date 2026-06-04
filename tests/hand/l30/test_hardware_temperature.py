from __future__ import annotations

import pytest

from tests.hand.l30.hardware_helpers import (
    assert_joint_tuple,
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


def test_l30_hardware_temperature_read_and_snapshot() -> None:
    require_full_hardware()
    settings = hardware_settings()

    with open_l30() as hand:
        temperature = hand.temperature.get_blocking(timeout_ms=settings.timeout_ms)
        snapshot = hand.temperature.get_snapshot()

    assert_joint_tuple(temperature.temperatures)
    assert snapshot is temperature
