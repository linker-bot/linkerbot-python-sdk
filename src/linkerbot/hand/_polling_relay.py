"""Relay coordination for polling requests with multi-frame responses."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Generic, TypeVar

from linkerbot.relay import DataRelay

T = TypeVar("T")
POLLING_RESPONSE_TIMEOUT_S = 0.1


@dataclass(frozen=True, slots=True)
class _RequestToken:
    generation: int
    owner: str


class _InFlightGate:
    def __init__(
        self,
        reset_response: Callable[[], None],
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._reset_response = reset_response
        self._clock = clock
        self._lock = threading.Lock()
        self._generation = 0
        self._token: _RequestToken | None = None
        self._deadline = 0.0

    def begin(
        self, timeout_s: float, *, owner: str, replace: bool = False
    ) -> _RequestToken | None:
        with self._lock:
            now = self._clock()
            if self._token is not None and not replace and now < self._deadline:
                return None
            self._generation += 1
            token = _RequestToken(self._generation, owner)
            self._token = token
            self._deadline = now + timeout_s
            self._reset_response()
            return token

    def finish(self, token: _RequestToken | None = None) -> bool:
        with self._lock:
            if self._token is None or (token is not None and token != self._token):
                return False
            self._token = None
            self._deadline = 0.0
            self._reset_response()
            return True

    def cancel_owner(self, owner: str) -> bool:
        with self._lock:
            if self._token is None or self._token.owner != owner:
                return False
            self._token = None
            self._deadline = 0.0
            self._reset_response()
            return True


class PollingDataRelay(Generic[T]):
    """Coordinate one response batch across polling and blocking callers."""

    def __init__(
        self,
        clear_pending: Callable[[], None],
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._gate = _InFlightGate(clear_pending, clock)
        self._send_lock = threading.Lock()
        self._relay = DataRelay[T]()

    def request(self, send: Callable[[], object], timeout_s: float) -> T:
        """Run a blocking request whose gate uses the caller's timeout."""

        token: _RequestToken | None = None

        def guarded_send() -> None:
            nonlocal token
            with self._send_lock:
                token = self._gate.begin(timeout_s, owner="blocking", replace=True)
                try:
                    send()
                except BaseException:
                    self._finish(token)
                    raise

        try:
            return self._relay.request(guarded_send, timeout_s)
        except BaseException:
            if token is not None:
                self._finish(token)
            raise

    def poll(
        self,
        send: Callable[[], object],
        timeout_s: float = POLLING_RESPONSE_TIMEOUT_S,
    ) -> bool:
        """Send a polling request unless the current response is still pending."""

        with self._send_lock:
            token = self._gate.begin(timeout_s, owner="polling")
            if token is None:
                return False
            try:
                send()
            except BaseException:
                self._finish(token)
                raise
        return True

    def cancel_polling(self) -> None:
        """Cancel only a polling-owned response batch."""

        self._gate.cancel_owner("polling")

    def push(self, data: T) -> None:
        """Complete the active batch and publish its assembled value."""

        self._finish()
        self._relay.push(data)

    def snapshot(self) -> T | None:
        return self._relay.snapshot()

    def set_sink(self, sink: Callable[[T], None] | None) -> None:
        self._relay.set_sink(sink)

    def _finish(self, token: _RequestToken | None = None) -> None:
        self._gate.finish(token)


__all__ = ["POLLING_RESPONSE_TIMEOUT_S", "PollingDataRelay"]
