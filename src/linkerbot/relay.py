"""Thread-safe data relay: cache + blocking wait + event sink."""

import math
import threading
from collections.abc import Callable
from typing import Generic, TypeVar, cast

from linkerbot.exceptions import TimeoutError, ValidationError

T = TypeVar("T")

_SENTINEL = object()


class DataRelay(Generic[T]):
    """Thread-safe data relay: cache + blocking wait + event sink.

    Combines three responsibilities shared by all sensor managers:
    1. Cache the latest data value (snapshot)
    2. Blocking wait with timeout for the next value
    3. Event sink callback for streaming
    """

    def __init__(self) -> None:
        self._latest: T | None = None
        self._waiters: list[tuple[threading.Event, dict[str, object]]] = []
        self._lock = threading.Lock()
        self._request_lock = threading.Lock()
        self._sink: Callable[[T], None] | None = None

    def snapshot(self) -> T | None:
        """Return the most recently pushed value, or None."""
        with self._lock:
            return self._latest

    def wait(self, timeout_s: float) -> T:
        """Block until the next push() call, or raise TimeoutError."""
        self._validate_timeout(timeout_s)
        return self._wait_for(self._register_waiter(), timeout_s)

    def request(self, send: Callable[[], object], timeout_s: float) -> T:
        """Register a waiter, send one request, then wait for its response.

        Requests on one relay are serialized so a response cannot complete two
        concurrent callers. Registering before ``send`` also captures transports
        that deliver a response synchronously from inside ``send``.
        """
        if not callable(send):
            raise ValidationError("send must be callable")
        self._validate_timeout(timeout_s)
        with self._request_lock:
            waiter = self._register_waiter()
            send_completed = False
            try:
                send()
                send_completed = True
            finally:
                if not send_completed:
                    self._discard_waiter(waiter)
            return self._wait_for(waiter, timeout_s)

    @staticmethod
    def _validate_timeout(timeout_s: float) -> None:
        if (
            not isinstance(timeout_s, (int, float))
            or isinstance(timeout_s, bool)
            or not math.isfinite(timeout_s)
            or timeout_s < 0
        ):
            raise ValidationError("timeout_s must be a finite, non-negative number")

    def _register_waiter(self) -> tuple[threading.Event, dict[str, object]]:
        event = threading.Event()
        result_holder: dict[str, object] = {"data": _SENTINEL}
        waiter = (event, result_holder)

        with self._lock:
            self._waiters.append(waiter)
        return waiter

    def _wait_for(
        self,
        waiter: tuple[threading.Event, dict[str, object]],
        timeout_s: float,
    ) -> T:
        event, result_holder = waiter
        if event.wait(timeout_s):
            if result_holder["data"] is _SENTINEL:
                raise TimeoutError(f"No data received within {timeout_s * 1000:.0f}ms")
            return cast(T, result_holder["data"])
        self._discard_waiter(waiter)
        raise TimeoutError(f"No data received within {timeout_s * 1000:.0f}ms")

    def _discard_waiter(
        self, waiter: tuple[threading.Event, dict[str, object]]
    ) -> None:
        with self._lock:
            if waiter in self._waiters:
                self._waiters.remove(waiter)

    def push(self, data: T) -> None:
        """Update cache, wake all waiters, and notify sink."""
        with self._lock:
            self._latest = data
            for event, result_holder in self._waiters:
                result_holder["data"] = data
                event.set()
            self._waiters.clear()

        if self._sink is not None:
            self._sink(data)

    def set_sink(self, sink: Callable[[T], None] | None) -> None:
        """Set the event sink callback."""
        self._sink = sink
