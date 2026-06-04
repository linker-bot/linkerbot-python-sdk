from __future__ import annotations

import pytest

from tests.hand.l30.hardware_helpers import (
    hardware_settings,
    open_l30,
    require_full_hardware,
    require_motion_allowed,
)

pytestmark = [
    pytest.mark.l30,
    pytest.mark.canfd,
    pytest.mark.hardware,
    pytest.mark.interactive,
]


def test_l30_hardware_control_enable_disable() -> None:
    require_full_hardware()
    require_motion_allowed()
    settings = hardware_settings()

    with open_l30() as hand:
        try:
            hand.control.enable(timeout_ms=settings.timeout_ms)
        finally:
            hand.control.disable(timeout_ms=settings.timeout_ms)
