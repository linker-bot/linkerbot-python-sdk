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


def test_l30_hardware_fault_read_snapshot_and_helpers() -> None:
    require_full_hardware()
    settings = hardware_settings()

    with open_l30() as hand:
        fault = hand.fault.get_blocking(timeout_ms=settings.timeout_ms)
        snapshot = hand.fault.get_snapshot()

    assert_joint_tuple(fault.faults)
    assert snapshot is fault
    assert isinstance(fault.has_voltage_fault(0), bool)
    assert isinstance(fault.has_magnetic_encoder_fault(0), bool)
    assert isinstance(fault.has_temperature_fault(0), bool)
    assert isinstance(fault.has_current_fault(0), bool)
    assert isinstance(fault.has_load_fault(0), bool)
