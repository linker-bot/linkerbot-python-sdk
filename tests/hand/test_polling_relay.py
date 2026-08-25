"""Tests for polling request timeout and ownership coordination."""

from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import can
import pytest

from linkerbot.exceptions import ValidationError
from linkerbot.hand._polling_relay import PollingDataRelay
from linkerbot.hand.l20lite.angle import AngleManager


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class _RecordingDispatcher:
    def __init__(self) -> None:
        self.callbacks: list[Callable[[can.Message], None]] = []
        self.sent: list[can.Message] = []

    def subscribe(self, callback: Callable[[can.Message], None]) -> None:
        self.callbacks.append(callback)

    def send(self, message: can.Message) -> None:
        self.sent.append(message)


def test_poll_retries_on_first_cycle_after_response_timeout() -> None:
    clock = _Clock()
    pending = [1]
    sends = 0
    relay = PollingDataRelay[int](pending.clear, clock=clock)

    def send() -> None:
        nonlocal sends
        sends += 1

    assert relay.poll(send, timeout_s=0.1)
    pending.append(2)
    clock.now = 0.099
    assert not relay.poll(send, timeout_s=0.1)
    assert pending == [2]

    clock.now = 0.1
    assert relay.poll(send, timeout_s=0.1)
    assert sends == 2
    assert pending == []


def test_cancel_polling_does_not_cancel_blocking_owner() -> None:
    clock = _Clock()
    pending = [1]
    relay = PollingDataRelay[int](pending.clear, clock=clock)

    def send() -> None:
        pending.append(2)
        relay.cancel_polling()
        assert pending == [2]
        relay.push(7)

    assert relay.request(send, 0.1) == 7
    assert pending == []


def test_cancel_polling_allows_immediate_next_round() -> None:
    pending = [1]
    sends = 0
    relay = PollingDataRelay[int](pending.clear)

    def send() -> None:
        nonlocal sends
        sends += 1
        pending.append(sends)

    assert relay.poll(send)
    relay.cancel_polling()
    assert pending == []
    assert relay.poll(send)
    assert sends == 2


def test_old_timeout_cleanup_does_not_clear_new_generation() -> None:
    clock = _Clock()
    pending: list[int] = []
    relay = PollingDataRelay[int](pending.clear, clock=clock)
    first_send_finished = threading.Event()

    def unanswered_send() -> None:
        pending.append(1)
        first_send_finished.set()

    with ThreadPoolExecutor(max_workers=1) as executor:
        first = executor.submit(relay.request, unanswered_send, 0.02)
        assert first_send_finished.wait(1.0)

        clock.now = 0.02
        assert relay.poll(lambda: pending.append(2), timeout_s=0.1)
        with pytest.raises(TimeoutError):
            first.result(timeout=1.0)

    assert pending == [2]
    clock.now = 0.119
    assert not relay.poll(lambda: pending.append(3), timeout_s=0.1)


def test_rejected_blocking_request_does_not_cancel_polling() -> None:
    pending: list[int] = []
    relay = PollingDataRelay[int](pending.clear)

    assert relay.poll(lambda: pending.append(1))
    with pytest.raises(ValidationError):
        relay.request(lambda: pending.append(2), float("nan"))

    assert pending == [1]
    assert not relay.poll(lambda: pending.append(3))


def test_poll_send_failure_cleans_gate_for_retry() -> None:
    pending: list[int] = []
    relay = PollingDataRelay[int](pending.clear)

    def failing_send() -> None:
        pending.append(1)
        raise RuntimeError("send failed")

    with pytest.raises(RuntimeError, match="send failed"):
        relay.poll(failing_send)

    assert pending == []
    assert relay.poll(lambda: pending.append(2))


def test_l20lite_angle_polling_retries_at_shared_deadline(tmp_path: Path) -> None:
    clock = _Clock()
    dispatcher = _RecordingDispatcher()
    manager = AngleManager(
        0x28,
        dispatcher,
        angle_mapping_path=tmp_path / "l20lite.toml",
    )
    manager._relay._gate._clock = clock

    manager._send_sense_request()
    assert [int(message.data[0]) for message in dispatcher.sent] == [0x01, 0x04]

    clock.now = 0.099
    manager._send_sense_request()
    assert len(dispatcher.sent) == 2

    clock.now = 0.1
    manager._send_sense_request()
    assert [int(message.data[0]) for message in dispatcher.sent] == [
        0x01,
        0x04,
        0x01,
        0x04,
    ]
