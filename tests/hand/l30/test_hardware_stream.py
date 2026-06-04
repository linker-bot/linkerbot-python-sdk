from __future__ import annotations

import pytest

from linkerbot.hand.l30 import AngleEvent
from tests.hand.l30.hardware_helpers import (
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


def test_l30_hardware_stream_receives_angle_event() -> None:
    require_full_hardware()
    settings = hardware_settings()

    with open_l30() as hand:
        stream = hand.stream()
        try:
            hand.start_periodic_reports(timeout_ms=settings.timeout_ms)
            event = stream.get(timeout=settings.timeout_ms / 1000)
        finally:
            hand.stop_stream()
            hand.stop_periodic_reports(timeout_ms=settings.timeout_ms)

    assert isinstance(event, AngleEvent)


def test_l30_hardware_stream_can_stop_without_events() -> None:
    require_full_hardware()

    with open_l30() as hand:
        stream = hand.stream()
        hand.stop_stream()

        with pytest.raises(StopIteration):
            stream.get(timeout=0.01)
