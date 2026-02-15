"""Thread-safe data relay: cache + blocking wait + event sink."""

import threading
from collections.abc import Callable
from typing import Generic, TypeVar

from linkerbot.exceptions import TimeoutError

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
        self._waiters: list[tuple[threading.Event, dict]] = []
        self._lock = threading.Lock()
        self._sink: Callable[[T], None] | None = None

    def snapshot(self) -> T | None:
        """Return the most recently pushed value, or None."""
        with self._lock:
            return self._latest

    def wait(self, timeout_s: float) -> T:
        """Block until the next push() call, or raise TimeoutError."""
        event = threading.Event()
        result_holder: dict[str, object] = {"data": _SENTINEL}

        with self._lock:
            self._waiters.append((event, result_holder))

        if event.wait(timeout_s):
            if result_holder["data"] is _SENTINEL:
                raise TimeoutError(f"No data received within {timeout_s * 1000:.0f}ms")
            return result_holder["data"]  # type: ignore[return-value]
        else:
            with self._lock:
                if (event, result_holder) in self._waiters:
                    self._waiters.remove((event, result_holder))
            raise TimeoutError(f"No data received within {timeout_s * 1000:.0f}ms")

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

    def set_sink(self, sink: Callable[[T], None]) -> None:
        """Set the event sink callback."""
        self._sink = sink
