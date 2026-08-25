"""Regression tests for classic five-finger force polling."""

from __future__ import annotations

import time
from typing import Any, cast

import can
import pytest

from linkerbot.hand.l6.force_sensor import ForceSensorManager as L6ForceManager
from linkerbot.hand.l20lite.force_sensor import (
    ForceSensorManager as L20LiteForceManager,
)
from linkerbot.hand.l25.force_sensor import ForceSensorManager as L25ForceManager
from linkerbot.hand.o6.force_sensor import ForceSensorManager as O6ForceManager


class _RecordingDispatcher:
    def __init__(self) -> None:
        self.callbacks: list[Any] = []
        self.sent: list[can.Message] = []

    def subscribe(self, callback: Any) -> None:
        self.callbacks.append(callback)

    def send(self, message: can.Message) -> None:
        self.sent.append(message)


@pytest.mark.parametrize(
    ("manager_type", "request_suffix"),
    (
        (L6ForceManager, 0xC6),
        (O6ForceManager, 0xA4),
        (L20LiteForceManager, 0xC6),
        (L25ForceManager, 0xC6),
    ),
)
def test_force_poll_sends_all_fingers_in_order_without_fixed_delay(
    monkeypatch: pytest.MonkeyPatch,
    manager_type: type[Any],
    request_suffix: int,
) -> None:
    def reject_sleep(_seconds: float) -> None:
        raise AssertionError("force polling must not impose an inter-finger delay")

    monkeypatch.setattr(time, "sleep", reject_sleep)
    dispatcher = _RecordingDispatcher()
    manager = manager_type(0x28, cast(Any, dispatcher))

    manager._send_sense_request()

    assert [list(message.data) for message in dispatcher.sent] == [
        [finger_command, request_suffix]
        for finger_command in (0xB1, 0xB2, 0xB3, 0xB4, 0xB5)
    ]
