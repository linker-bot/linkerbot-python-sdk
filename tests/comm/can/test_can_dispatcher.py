import math
import threading
import time
from typing import Any

import can
import pytest

from linkerbot.comm.can import CANMessageDispatcher
from linkerbot.exceptions import CANError, ValidationError


class FakeBus:
    def __init__(self) -> None:
        self.sent: list[can.Message] = []
        self.send_timeouts: list[float | None] = []
        self.send_event = threading.Event()
        self.shutdown_calls = 0
        self.receive_error: Exception | None = None

    def recv(self, timeout: float) -> can.Message | None:
        if self.receive_error is not None:
            error = self.receive_error
            self.receive_error = None
            raise error
        time.sleep(min(timeout, 0.001))
        return None

    def send(self, message: can.Message, timeout: float | None = None) -> None:
        self.sent.append(message)
        self.send_timeouts.append(timeout)
        self.send_event.set()

    def shutdown(self) -> None:
        self.shutdown_calls += 1


def make_dispatcher(
    monkeypatch: pytest.MonkeyPatch,
    bus: FakeBus,
    **kwargs: Any,
) -> CANMessageDispatcher:
    monkeypatch.setattr("linkerbot.comm.can.can.can.Bus", lambda **options: bus)
    return CANMessageDispatcher(interface_name="vcan0", **kwargs)


def test_send_pacing_sleeps_instead_of_busy_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bus = FakeBus()
    dispatcher = make_dispatcher(monkeypatch, bus)
    sleep_called = threading.Event()
    pacing_sleeps: list[float] = []
    original_sleep = time.sleep
    clock = iter([10.0, 10.0001])

    def record_sleep(duration: float) -> None:
        if duration < dispatcher.SEND_INTERVAL_S:
            pacing_sleeps.append(duration)
            sleep_called.set()
        original_sleep(duration)

    monkeypatch.setattr("linkerbot.comm.can.can.time.monotonic", lambda: next(clock))
    monkeypatch.setattr("linkerbot.comm.can.can.time.sleep", record_sleep)
    try:
        dispatcher.send(can.Message(arbitration_id=1, data=b"x"))
        assert bus.send_event.wait(timeout=1.0)
        assert sleep_called.wait(timeout=1.0)
        assert pacing_sleeps == [pytest.approx(0.0002)]
    finally:
        dispatcher.stop()


def test_send_uses_finite_bus_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    bus = FakeBus()
    dispatcher = make_dispatcher(monkeypatch, bus)
    try:
        dispatcher.send(can.Message(arbitration_id=1, data=b"x"))

        assert bus.send_event.wait(timeout=1.0)
        assert bus.send_timeouts == [dispatcher.SEND_TIMEOUT_S]
        assert dispatcher.SEND_TIMEOUT_S > 0
        assert math.isfinite(dispatcher.SEND_TIMEOUT_S)
    finally:
        dispatcher.stop()


def test_transient_receive_error_uses_millisecond_backoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bus = FakeBus()
    bus.receive_error = CANError("transient")
    sleep_durations: list[float] = []
    original_sleep = time.sleep

    def record_sleep(duration: float) -> None:
        sleep_durations.append(duration)
        original_sleep(min(duration, 0.001))

    monkeypatch.setattr("linkerbot.comm.can.can.time.sleep", record_sleep)
    dispatcher = make_dispatcher(monkeypatch, bus, max_consecutive_errors=2)
    try:
        deadline = time.monotonic() + 1.0
        while (
            not any(duration >= 0.004 for duration in sleep_durations)
            and time.monotonic() < deadline
        ):
            original_sleep(0.001)
        backoffs = [duration for duration in sleep_durations if duration >= 0.004]
        assert backoffs
        assert min(backoffs) <= 0.005
    finally:
        dispatcher.stop()


@pytest.mark.parametrize("value", [0, -1, True, 1.5])
def test_invalid_error_threshold_is_rejected_before_opening_bus(
    monkeypatch: pytest.MonkeyPatch,
    value: object,
) -> None:
    opened = False

    def open_bus(**options: Any) -> FakeBus:
        nonlocal opened
        opened = True
        return FakeBus()

    monkeypatch.setattr("linkerbot.comm.can.can.can.Bus", open_bus)

    with pytest.raises(ValidationError, match="positive int"):
        CANMessageDispatcher(
            "vcan0",
            max_consecutive_errors=value,  # ty: ignore[invalid-argument-type]
        )

    assert opened is False


def test_stop_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    bus = FakeBus()
    dispatcher = make_dispatcher(monkeypatch, bus)

    dispatcher.stop()
    dispatcher.stop()

    assert bus.shutdown_calls == 1


class ShutdownInterruptsSendBus(FakeBus):
    def __init__(self) -> None:
        super().__init__()
        self.send_started = threading.Event()
        self.shutdown_event = threading.Event()

    def send(self, message: can.Message, timeout: float | None = None) -> None:
        self.sent.append(message)
        self.send_timeouts.append(timeout)
        self.send_started.set()
        self.shutdown_event.wait()

    def shutdown(self) -> None:
        super().shutdown()
        self.shutdown_event.set()


def test_stop_shuts_down_bus_to_interrupt_blocked_send(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("linkerbot.comm.can.can.THREAD_JOIN_TIMEOUT_S", 0.01)
    bus = ShutdownInterruptsSendBus()
    dispatcher = make_dispatcher(monkeypatch, bus)
    dispatcher.send(can.Message(arbitration_id=1, data=b"x"))
    assert bus.send_started.wait(timeout=1.0)

    dispatcher.stop()

    assert bus.shutdown_calls == 1
    assert not dispatcher._recv_thread.is_alive()
    assert not dispatcher._send_thread.is_alive()


def test_concurrent_stop_shuts_down_bus_once_and_joins_workers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("linkerbot.comm.can.can.THREAD_JOIN_TIMEOUT_S", 0.01)
    bus = ShutdownInterruptsSendBus()
    dispatcher = make_dispatcher(monkeypatch, bus)
    dispatcher.send(can.Message(arbitration_id=1, data=b"x"))
    assert bus.send_started.wait(timeout=1.0)

    start = threading.Barrier(3)
    errors: list[Exception] = []

    def stop_dispatcher() -> None:
        start.wait()
        try:
            dispatcher.stop()
        except Exception as error:
            errors.append(error)

    callers = [threading.Thread(target=stop_dispatcher) for _ in range(2)]
    for caller in callers:
        caller.start()
    start.wait()
    for caller in callers:
        caller.join(timeout=1.0)

    assert errors == []
    assert all(not caller.is_alive() for caller in callers)
    assert bus.shutdown_calls == 1
    assert not dispatcher._recv_thread.is_alive()
    assert not dispatcher._send_thread.is_alive()


def test_stop_reports_worker_that_ignores_bus_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("linkerbot.comm.can.can.THREAD_JOIN_TIMEOUT_S", 0.01)
    release_send = threading.Event()

    class StuckSendBus(FakeBus):
        def send(self, message: can.Message, timeout: float | None = None) -> None:
            self.send_event.set()
            release_send.wait()

    bus = StuckSendBus()
    dispatcher = make_dispatcher(monkeypatch, bus)
    dispatcher.send(can.Message(arbitration_id=1, data=b"x"))
    assert bus.send_event.wait(timeout=1.0)

    try:
        with pytest.raises(RuntimeError, match="send_loop"):
            dispatcher.stop()
        assert bus.shutdown_calls == 1
    finally:
        release_send.set()
        dispatcher._send_thread.join(timeout=1.0)

    assert not dispatcher._send_thread.is_alive()
