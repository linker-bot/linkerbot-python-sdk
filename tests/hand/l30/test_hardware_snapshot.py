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


def test_l30_hardware_snapshot_after_reading_core_sensors() -> None:
    require_full_hardware()
    settings = hardware_settings()

    with open_l30() as hand:
        hand.angle.get_blocking(timeout_ms=settings.timeout_ms)
        hand.speed.get_blocking(timeout_ms=settings.timeout_ms)
        hand.current.get_blocking(timeout_ms=settings.timeout_ms)
        hand.temperature.get_blocking(timeout_ms=settings.timeout_ms)
        hand.fault.get_blocking(timeout_ms=settings.timeout_ms)
        snapshot = hand.get_snapshot()

    assert snapshot.angle is not None
    assert snapshot.speed is not None
    assert snapshot.current is not None
    assert snapshot.temperature is not None
    assert snapshot.fault is not None
    assert_joint_tuple(tuple(snapshot.angle.angles))
    assert_joint_tuple(snapshot.speed.speeds)
    assert_joint_tuple(snapshot.current.currents)
    assert_joint_tuple(snapshot.temperature.temperatures)
    assert_joint_tuple(snapshot.fault.faults)
