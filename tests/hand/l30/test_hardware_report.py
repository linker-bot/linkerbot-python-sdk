from __future__ import annotations

import pytest

from linkerbot.hand.l30 import ReportSource
from tests.hand.l30.hardware_helpers import (
    assert_joint_tuple,
    hardware_settings,
    open_l30,
    require_full_hardware,
    wait_for_angle_snapshot,
)

pytestmark = [
    pytest.mark.l30,
    pytest.mark.canfd,
    pytest.mark.hardware,
    pytest.mark.interactive,
]


def test_l30_hardware_report_start_default_and_disable_all() -> None:
    require_full_hardware()
    settings = hardware_settings()

    with open_l30() as hand:
        try:
            hand.report.start_default(timeout_ms=settings.timeout_ms)
            angle = wait_for_angle_snapshot(hand, settings.timeout_ms)
        finally:
            hand.report.disable_all(timeout_ms=settings.timeout_ms)

    assert_joint_tuple(tuple(angle.angles))


def test_l30_hardware_report_configure_and_disable_angle() -> None:
    require_full_hardware()
    settings = hardware_settings()

    with open_l30() as hand:
        try:
            hand.report.configure(
                ReportSource.ANGLE,
                enabled=True,
                timeout_ms=settings.timeout_ms,
            )
            angle = wait_for_angle_snapshot(hand, settings.timeout_ms)
        finally:
            hand.report.disable(ReportSource.ANGLE, timeout_ms=settings.timeout_ms)

    assert_joint_tuple(tuple(angle.angles))
