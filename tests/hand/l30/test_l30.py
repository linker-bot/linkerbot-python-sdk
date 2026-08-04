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
    assert event.data.angles.to_raw() == [7] * 17
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


@pytest.mark.parametrize("interval", [0.0, True, float("nan"), float("inf")])
def test_start_polling_rejects_invalid_interval(interval: float) -> None:
    hand = L30(dispatcher=FakeDispatcher(), auto_start_periodic=False)

    with pytest.raises(ValidationError):
        hand.start_polling({SensorSource.ANGLE: interval})

    hand.close()


def test_start_polling_rolls_back_when_thread_start_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hand = L30(dispatcher=FakeDispatcher(), auto_start_periodic=False)
    real_thread = threading.Thread
    starts = 0

    class FlakyThread(real_thread):
        def start(self) -> None:
            nonlocal starts
            starts += 1
            if starts == 2:
                raise RuntimeError("thread.start failed")
            super().start()

    monkeypatch.setattr(threading, "Thread", FlakyThread)

    with pytest.raises(RuntimeError, match="thread.start failed"):
        hand.start_polling({SensorSource.ANGLE: 0.01, SensorSource.CURRENT: 0.01})

    assert hand._polling_threads == {}
    assert hand._stop_polling.is_set()
    hand.close()


def test_l30_rejects_invalid_interface_type() -> None:
    with pytest.raises(ValidationError, match="interface_type"):
        L30(
            interface_type="usbcan",  # ty: ignore[invalid-argument-type]
            dispatcher=FakeDispatcher(),
            auto_start_periodic=False,
        )


@pytest.mark.parametrize("frame_type", [-1, 256, True, "0x04"])
def test_l30_rejects_invalid_frame_type(frame_type) -> None:
    with pytest.raises(ValidationError, match="frame_type"):
        L30(
            frame_type=frame_type,
            dispatcher=FakeDispatcher(),
            auto_start_periodic=False,
        )


def test_l30_defaults_outgoing_messages_to_fd_without_brs() -> None:
    dispatcher = FakeDispatcher()
    hand = L30(
        dispatcher=dispatcher,
        auto_start_periodic=False,
    )

    hand.angle.set_angles([0] * 17)

    assert dispatcher.sent[-1].frame_type == 0x04
    hand.close()


def test_l30_allows_explicit_brs_frame_type() -> None:
    dispatcher = FakeDispatcher()
    hand = L30(
        frame_type=0x0C,
        dispatcher=dispatcher,
        auto_start_periodic=False,
    )

    hand.angle.set_angles([0] * 17)

    assert dispatcher.sent[-1].frame_type == 0x0C
    hand.close()


def test_l30_socketcan_requires_channel() -> None:
    with pytest.raises(ValidationError, match="channel"):
        L30(interface_type="socketcan", auto_start_periodic=False)


def test_l30_socketcan_routes_to_socketcan_backend(monkeypatch) -> None:
    """interface_type='socketcan' must construct SocketCANFDBackend with the
    user-supplied channel and bitrates."""
    captured: dict[str, object] = {}

    class _StubBackend:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

        def send(self, message, timeout_ms=10):
            pass

        def receive(self, max_frames=64, timeout_ms=10):
            return []

        def close(self):
            pass

    import linkerbot.hand.l30.l30 as l30_module

    monkeypatch.setattr(l30_module, "SocketCANFDBackend", _StubBackend)

    hand = L30(
        interface_type="socketcan",
        channel="can3",
        bitrate=2_000_000,
        data_bitrate=4_000_000,
        auto_reconfigure=True,
        auto_start_periodic=False,
    )
    try:
        assert captured == {
            "channel": "can3",
            "bitrate": 2_000_000,
            "data_bitrate": 4_000_000,
            "auto_reconfigure": True,
        }
    finally:
        hand.close()


def test_on_bus_error_during_construction_does_not_attribute_error(
    monkeypatch,
) -> None:
    """If the dispatcher's recv thread reports a bus error before __init__ has
    finished assigning every field, on_bus_error -> close() must run without
    raising AttributeError on _stop_polling / _polling_threads / etc."""

    class EagerlyFailingDispatcher(FakeDispatcher):
        def __init__(self, *, on_bus_error=None, **kwargs) -> None:
            super().__init__()
            if on_bus_error is not None:
                on_bus_error(RuntimeError("simulated bus error"))

    import linkerbot.hand.l30.l30 as l30_module

    monkeypatch.setattr(l30_module, "CANFDMessageDispatcher", EagerlyFailingDispatcher)

    # Construction should complete (close() got called early but did not
    # raise); the resulting hand reports itself closed.
    hand = L30(auto_start_periodic=False)
    assert hand.is_closed()


def _ack(dispatcher: FakeDispatcher, arbitration_id: int) -> None:
    dispatcher.inject(CANFDMessage(arbitration_id=arbitration_id, data=ack_payload()))
