"""Tests for the close-aware iterable queue."""

import math
import queue
import threading
import time

import pytest

from linkerbot.exceptions import StateError
from linkerbot.queue import IterableQueue


def test_get_honors_timeout() -> None:
    items = IterableQueue[int]()

    started = time.monotonic()
    with pytest.raises(queue.Empty):
        items.get(timeout=0.02)

    elapsed = time.monotonic() - started
    assert 0.015 <= elapsed < 0.2


def test_close_wakes_blocked_consumer() -> None:
    items = IterableQueue[int]()
    started = threading.Event()
    stopped = threading.Event()

    def consume() -> None:
        started.set()
        with pytest.raises(StopIteration):
            items.get()
        stopped.set()

    thread = threading.Thread(target=consume)
    thread.start()
    assert started.wait(timeout=0.5)
    time.sleep(0.01)
    items.close()
    thread.join(timeout=0.5)

    assert stopped.is_set()


def test_close_wakes_producer_blocked_on_full_queue() -> None:
    items = IterableQueue[int](maxsize=1)
    items.put(1)
    started = threading.Event()
    stopped = threading.Event()

    def produce() -> None:
        started.set()
        with pytest.raises(StateError, match="closed queue"):
            items.put(2)
        stopped.set()

    thread = threading.Thread(target=produce)
    thread.start()
    assert started.wait(timeout=0.5)
    time.sleep(0.01)
    items.close()
    thread.join(timeout=0.5)

    assert stopped.is_set()
    assert items.get_nowait() == 1
    with pytest.raises(StopIteration):
        items.get_nowait()


def test_put_honors_timeout_when_queue_is_full() -> None:
    items = IterableQueue[int](maxsize=1)
    items.put(1)

    started = time.monotonic()
    with pytest.raises(queue.Full):
        items.put(2, timeout=0.02)

    elapsed = time.monotonic() - started
    assert 0.015 <= elapsed < 0.2


def test_get_with_short_timeout_observes_close_as_stop_iteration() -> None:
    items = IterableQueue[int]()
    started = threading.Event()
    result: list[type[BaseException]] = []

    def consume() -> None:
        started.set()
        try:
            items.get(timeout=0.05)
        except BaseException as error:
            result.append(type(error))

    thread = threading.Thread(target=consume)
    thread.start()
    assert started.wait(timeout=0.5)
    time.sleep(0.01)
    items.close()
    thread.join(timeout=0.5)

    assert result == [StopIteration]


def test_blocked_producer_wakes_when_capacity_is_released() -> None:
    items = IterableQueue[int](maxsize=1)
    items.put(1)
    started = threading.Event()
    completed = threading.Event()

    def produce() -> None:
        started.set()
        items.put(2)
        completed.set()

    thread = threading.Thread(target=produce)
    thread.start()
    assert started.wait(timeout=0.5)
    time.sleep(0.01)
    assert items.get() == 1
    assert completed.wait(timeout=0.05)
    thread.join(timeout=0.5)
    assert items.get_nowait() == 2


def test_closed_queue_drains_in_fifo_order_before_iteration_stops() -> None:
    items = IterableQueue[int]()
    items.put(1)
    items.put(2)
    items.close()

    assert list(items) == [1, 2]
    with pytest.raises(StateError, match="closed queue"):
        items.put(3)


@pytest.mark.parametrize("method", ["get", "put"])
def test_nonblocking_operation_rejects_timeout(method: str) -> None:
    items = IterableQueue[int]()

    with pytest.raises(ValueError, match="block is False"):
        if method == "get":
            items.get(block=False, timeout=1.0)
        else:
            items.put(0, block=False, timeout=1.0)


@pytest.mark.parametrize("timeout", [-1.0, math.inf, math.nan, True, "1"])
@pytest.mark.parametrize("method", ["get", "put"])
def test_blocking_operation_rejects_invalid_timeout(
    timeout: object, method: str
) -> None:
    items = IterableQueue[int]()

    with pytest.raises(ValueError, match="finite, non-negative"):
        if method == "get":
            items.get(timeout=timeout)  # ty: ignore[invalid-argument-type]
        else:
            items.put(0, timeout=timeout)  # ty: ignore[invalid-argument-type]
