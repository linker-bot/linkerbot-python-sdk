"""Tests for synchronous relay request coordination."""

import threading

import pytest

from linkerbot.exceptions import TimeoutError
from linkerbot.relay import DataRelay


def test_request_captures_response_pushed_during_send() -> None:
    relay = DataRelay[int]()

    assert relay.request(lambda: relay.push(42), 0.1) == 42


def test_request_cleans_waiter_when_send_raises() -> None:
    relay = DataRelay[int]()
    error = RuntimeError("send failed")

    def fail() -> None:
        raise error

    with pytest.raises(RuntimeError) as raised:
        relay.request(fail, 0.1)
    assert raised.value is error

    relay.push(1)
    assert relay.request(lambda: relay.push(2), 0.1) == 2


def test_request_does_not_reuse_response_after_timeout() -> None:
    relay = DataRelay[int]()

    with pytest.raises(TimeoutError):
        relay.request(lambda: None, 0.0)

    relay.push(1)
    assert relay.request(lambda: relay.push(2), 0.1) == 2


def test_request_serializes_concurrent_calls() -> None:
    relay = DataRelay[int]()
    first_sent = threading.Event()
    release_first = threading.Event()
    second_sent = threading.Event()
    results: dict[str, int] = {}

    def first_send() -> None:
        first_sent.set()
        assert release_first.wait(1.0)
        relay.push(1)

    def second_send() -> None:
        second_sent.set()
        relay.push(2)

    first = threading.Thread(
        target=lambda: results.__setitem__("first", relay.request(first_send, 1.0))
    )
    second = threading.Thread(
        target=lambda: results.__setitem__("second", relay.request(second_send, 1.0))
    )

    first.start()
    assert first_sent.wait(1.0)
    second.start()
    assert not second_sent.wait(0.05)
    release_first.set()
    first.join(timeout=1.0)
    second.join(timeout=1.0)

    assert not first.is_alive()
    assert not second.is_alive()
    assert results == {"first": 1, "second": 2}
