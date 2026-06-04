from __future__ import annotations

import threading

import pytest

from linkerbot.comm.canfd import CANFDMessage
from linkerbot.exceptions import StateError, ValidationError
from linkerbot.hand.l30 import L30
from linkerbot.hand.l30.events import AngleEvent, SensorSource
from linkerbot.hand.l30.protocol import ack_payload
from tests.hand.l30.fakes import FakeDispatcher

pytestmark = [pytest.mark.l30, pytest.mark.canfd]


def test_l30_exports_context_manager_and_closes_owned_resources() -> None:
    dispatcher = FakeDispatcher()

    with L30(dispatcher=dispatcher, auto_start_periodic=False) as hand:
        assert not hand.is_closed()

    assert hand.is_closed()
    assert not dispatcher.stopped


def test_l30_close_is_idempotent_and_operations_after_close_fail() -> None:
    hand = L30(dispatcher=FakeDispatcher(), auto_start_periodic=False)

    hand.close()
    hand.close()

    with pytest.raises(StateError):
        hand.stream()


def test_l30_auto_start_periodic_sends_default_angle_report_config() -> None:
    dispatcher = FakeDispatcher()
    result: list[L30] = []

    thread = threading.Thread(target=lambda: result.append(L30(dispatcher=dispatcher)))
    thread.start()
    _ack(dispatcher, 0x02802008)
    thread.join(timeout=1)

    assert dispatcher.sent[0].arbitration_id == 0x02802100
    assert dispatcher.sent[0].data == bytes.fromhex("09 00 01 00 00 00 14 00 00 00 00")
    result[0].close()


def test_stream_receives_periodic_angle_events() -> None:
    dispatcher = FakeDispatcher()
    hand = L30(dispatcher=dispatcher, auto_start_periodic=False)
    stream = hand.stream()

    dispatcher.inject(
        CANFDMessage(
            arbitration_id=0x00802008, data=bytes([0x22, 0]) + b"\x00\x07" * 17
        )
    )
    event = stream.get(timeout=1)

    assert isinstance(event, AngleEvent)
    assert event.data.angles.to_list() == [7] * 17
    hand.close()


def test_start_polling_uses_one_shot_query_parent() -> None:
    dispatcher = FakeDispatcher()
    hand = L30(dispatcher=dispatcher, auto_start_periodic=False)

    hand.start_polling({SensorSource.ANGLE: 0.01})
    while not dispatcher.sent:
        pass
    hand.stop_polling()

    assert dispatcher.sent[0].arbitration_id == 0x00A02100
    hand.close()


def test_start_polling_rejects_invalid_interval() -> None:
    hand = L30(dispatcher=FakeDispatcher(), auto_start_periodic=False)

    with pytest.raises(ValidationError):
        hand.start_polling({SensorSource.ANGLE: 0})

    hand.close()


def _ack(dispatcher: FakeDispatcher, arbitration_id: int) -> None:
    dispatcher.inject(CANFDMessage(arbitration_id=arbitration_id, data=ack_payload()))
