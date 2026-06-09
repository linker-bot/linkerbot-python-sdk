from __future__ import annotations

import threading
import time

import pytest

from linkerbot.exceptions import StateError, ValidationError
from linkerbot.hand.o20 import O20, protocol
from linkerbot.hand.o20.events import AngleEvent, SensorSource
from tests.hand.o20.fakes import FakeDispatcher

pytestmark = [pytest.mark.o20, pytest.mark.canfd]


def test_o20_uses_right_device_id_by_default() -> None:
    dispatcher = FakeDispatcher()

    with O20(side="right", dispatcher=dispatcher) as hand:
        assert hand.device_id == protocol.O20_DEVICE_ID_RIGHT


def test_o20_resolves_left_device_id_from_side() -> None:
    dispatcher = FakeDispatcher()

    with O20(side="left", dispatcher=dispatcher) as hand:
        assert hand.device_id == protocol.O20_DEVICE_ID_LEFT


def test_o20_explicit_device_id_overrides_side() -> None:
    dispatcher = FakeDispatcher()

    with O20(side="right", device_id=0x55, dispatcher=dispatcher) as hand:
        assert hand.device_id == 0x55


def test_o20_rejects_invalid_side() -> None:
    with pytest.raises(ValidationError):
        O20(side="middle", dispatcher=FakeDispatcher())  # type: ignore[arg-type]


def test_o20_close_is_idempotent_and_operations_after_close_fail() -> None:
    hand = O20(dispatcher=FakeDispatcher())

    hand.close()
    hand.close()

    with pytest.raises(StateError):
        hand.stream()


def test_o20_does_not_stop_externally_owned_dispatcher() -> None:
    dispatcher = FakeDispatcher()

    with O20(dispatcher=dispatcher) as hand:
        assert not hand.is_closed()

    assert hand.is_closed()
    assert dispatcher.stopped is False


def test_owned_dispatcher_is_stopped_when_construction_fails(monkeypatch) -> None:
    """If client/manager construction raises, the SDK-owned dispatcher must be
    stopped so the recv/send threads do not leak."""
    created: list[FakeDispatcher] = []

    class TrackedDispatcher(FakeDispatcher):
        def __init__(self, **kwargs) -> None:
            super().__init__()
            created.append(self)

    def raise_during_client(*args, **kwargs):
        raise RuntimeError("simulated client failure")

    import linkerbot.hand.o20.o20 as o20_module

    monkeypatch.setattr(o20_module, "CANFDMessageDispatcher", TrackedDispatcher)
    monkeypatch.setattr(o20_module, "O20Client", raise_during_client)

    with pytest.raises(RuntimeError, match="simulated client failure"):
        O20(side="right")

    assert len(created) == 1
    assert created[0].stopped is True


def test_dunder_del_swallows_close_errors(monkeypatch) -> None:
    """__del__ runs at GC time when many things can be in a weird state.
    A failure inside close() must not propagate as 'Exception ignored in
    __del__' noise."""
    hand = O20(dispatcher=FakeDispatcher())

    def boom() -> None:
        raise RuntimeError("simulated close failure")

    monkeypatch.setattr(hand, "close", boom)

    # __del__ must not re-raise.
    hand.__del__()


def test_on_bus_error_during_construction_does_not_attribute_error(
    monkeypatch,
) -> None:
    """If the dispatcher's recv thread reports a bus error before __init__ has
    finished assigning every field, on_bus_error -> close() must still run
    without raising AttributeError."""

    class EagerlyFailingDispatcher(FakeDispatcher):
        def __init__(self, *, on_bus_error=None, **kwargs) -> None:
            super().__init__()
            # Simulate the recv thread reporting a fatal bus error the moment
            # the dispatcher starts, while the parent O20.__init__ has only
            # initialized its simple fields.
            if on_bus_error is not None:
                on_bus_error(RuntimeError("simulated bus error"))

    import linkerbot.hand.o20.o20 as o20_module

    monkeypatch.setattr(o20_module, "CANFDMessageDispatcher", EagerlyFailingDispatcher)

    # Construction should complete (close() got called early but did not
    # raise); the resulting hand reports itself closed and surfaces the bus
    # error on the next API call.
    hand = O20(side="right")

    assert hand.is_closed()
    with pytest.raises((StateError, Exception)):
        hand.angle.get_blocking(timeout_ms=10)


def test_get_snapshot_returns_none_for_uninitialized_managers() -> None:
    with O20(dispatcher=FakeDispatcher()) as hand:
        snapshot = hand.get_snapshot()

        assert snapshot.angle is None
        assert snapshot.speed is None
        assert snapshot.timestamp > 0


def test_stream_emits_angle_event_after_blocking_read() -> None:
    response = b"".join(
        value.to_bytes(2, "little", signed=True) for value in [*range(1, 17), 0]
    )
    dispatcher = FakeDispatcher(responses={protocol.O20_REG_CURRENT_POS: response})

    with O20(dispatcher=dispatcher) as hand:
        stream = hand.stream()
        hand.angle.get_blocking(timeout_ms=200)
        event = stream.get(timeout=1)

        assert isinstance(event, AngleEvent)
        assert event.data.angles.to_list() == list(range(1, 17))


def test_start_polling_rejects_invalid_interval() -> None:
    with O20(dispatcher=FakeDispatcher()) as hand:
        with pytest.raises(ValidationError):
            hand.start_polling({SensorSource.ANGLE: 0})


def test_close_marks_closed_before_releasing_resources(monkeypatch) -> None:
    """If a release step raises, _closed must already be True so a retried
    close() does not double-release."""
    hand = O20(dispatcher=FakeDispatcher())

    call_count = {"stop_polling": 0}
    original_stop_polling = hand.stop_polling

    def failing_stop_polling() -> None:
        call_count["stop_polling"] += 1
        original_stop_polling()
        raise RuntimeError("simulated stop failure")

    monkeypatch.setattr(hand, "stop_polling", failing_stop_polling)

    with pytest.raises(RuntimeError, match="simulated stop failure"):
        hand.close()

    assert hand.is_closed()
    # Second close is a no-op; stop_polling must not run again.
    hand.close()
    assert call_count["stop_polling"] == 1


def test_start_polling_rolls_back_when_a_thread_fails_to_start(
    monkeypatch,
) -> None:
    """If thread.start() raises mid-loop, every thread that did start must
    be torn down before the exception propagates."""
    started = {"count": 0}

    real_thread = threading.Thread

    class FlakyThread(real_thread):  # type: ignore[misc, valid-type]
        def start(self) -> None:
            started["count"] += 1
            if started["count"] == 2:
                raise RuntimeError("thread.start failed")
            super().start()

    monkeypatch.setattr(threading, "Thread", FlakyThread)

    response = b"".join(
        value.to_bytes(2, "little", signed=True) for value in [*range(1, 17), 0]
    )
    dispatcher = FakeDispatcher(responses={protocol.O20_REG_CURRENT_POS: response})

    with O20(dispatcher=dispatcher) as hand:
        with pytest.raises(RuntimeError, match="thread.start failed"):
            hand.start_polling({SensorSource.ANGLE: 0.01, SensorSource.CURRENT: 0.01})
        # Recovery: no polling threads survive a partial start.
        assert hand._polling_threads == {}
        assert hand._stop_polling.is_set()


def test_start_polling_uses_register_read_for_angle() -> None:
    response = b"".join(
        value.to_bytes(2, "little", signed=True) for value in [*range(1, 17), 0]
    )
    dispatcher = FakeDispatcher(responses={protocol.O20_REG_CURRENT_POS: response})

    with O20(dispatcher=dispatcher) as hand:
        hand.start_polling({SensorSource.ANGLE: 0.01})
        deadline = time.monotonic() + 1.0
        while not dispatcher.sent and time.monotonic() < deadline:
            time.sleep(0.001)
        hand.stop_polling()

    assert dispatcher.sent, "polling thread did not send any frames within 1s"
    assert dispatcher.sent[0].arbitration_id == 0x00206000
