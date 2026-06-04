from __future__ import annotations

import pytest

from tests.hand.l30.hardware_helpers import (
    assert_joint_tuple,
    hardware_settings,
    open_l30,
    require_smoke_or_full_hardware,
)

pytestmark = [
    pytest.mark.l30,
    pytest.mark.canfd,
    pytest.mark.hardware,
    pytest.mark.interactive,
]


def test_l30_hardware_open_and_read_angle_snapshot() -> None:
    require_smoke_or_full_hardware()
    settings = hardware_settings()

    with open_l30() as hand:
        angle = hand.angle.get_blocking(timeout_ms=settings.timeout_ms)

    assert_joint_tuple(tuple(angle.angles))
