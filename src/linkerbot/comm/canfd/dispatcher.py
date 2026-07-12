"""Threaded CANFD message dispatcher."""

import logging
import queue
import threading
import time
from collections.abc import Callable
from pathlib import Path

from linkerbot.exceptions import CANError

from .ctypes_backend import CANFDInterface
from .types import CANFDBackend, CANFDConfigOptions, CANFDMessage

DEFAULT_MAX_CONSECUTIVE_ERRORS = 10
RECEIVE_BATCH_SIZE = 64
RECEIVE_TIMEOUT_MS = 10
SEND_QUEUE_GET_TIMEOUT_S = 0.01
THREAD_JOIN_TIMEOUT_S = 1.0
# Tight error backoff: a transient USB hiccup should recover in milliseconds,
# not pause the whole bus for seconds. Previously 0.1/1.0 made a single USB
# stutter cascade into ~5.5 s of bus silence before the dispatcher gave up.
ERROR_BACKOFF_BASE_S = 0.005
ERROR_BACKOFF_MAX_S = 0.05


class CANFDMessageDispatcher:
    """Thread-safe CANFD dispatcher with publish-subscribe message routing."""

    SEND_QUEUE_SIZE = 2000
    # Default off: the vendor USB stack already paces transmits, and any
    # positive interval ends up sleeping the send thread. Subclasses or callers
    # that want explicit pacing can override this class attribute. The legacy
    # 300 µs busy-wait has been removed entirely — see Commit 2 in the redesign
    # plan for rationale.
    SEND_INTERVAL_S = 0.0
    # Maximum frames coalesced into a single vendor call when the backend
    # exposes ``send_batch``. 32 leaves substantial headroom under the
    # vendor's 100-frame ceiling while keeping per-batch latency bounded.
    # Override on a subclass if a workload needs different latency/throughput
    # tradeoffs.
    SEND_BATCH_MAX = 32

    def __init__(
        self,
        device_index: int = 0,
        channel_index: int = 0,
        library_path: str | Path | None = None,
        config: CANFDConfigOptions | None = None,
        on_bus_error: Callable[[Exception], None] | None = None,
        max_consecutive_errors: int = DEFAULT_MAX_CONSECUTIVE_ERRORS,
        interface: CANFDBackend | None = None,
    ) -> None:
        """Initialize dispatcher threads for one CANFD interface.

        ``interface`` accepts any object satisfying ``CANFDBackend`` (the
        ctypes ``CANFDInterface`` and the new SocketCAN FD backend both do).
        When omitted, the dispatcher constructs a vendor ``CANFDInterface``
        using ``device_index`` / ``channel_index`` / ``library_path`` / ``config``,
        preserving the original behaviour.
        """
        self._interface: CANFDBackend = interface or CANFDInterface(
            device_index=device_index,
            channel_index=channel_index,
            library_path=library_path,
            config=config,
        )
        self._subscribers: list[Callable[[CANFDMessage], None]] = []
        # subscribe_filter targets: only invoked when the predicate returns
        # True. Avoids O(N) fan-out when N L30Client objects share one bus —
        # each client pre-filters by (dst_id, src_id) in O(1).
        self._filtered_subscribers: list[
            tuple[
                Callable[[CANFDMessage], bool],
                Callable[[CANFDMessage], None],
            ]
        ] = []
        self._subscribers_lock = threading.Lock()
        self._running = True
        self._logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self._send_queue: queue.Queue[CANFDMessage] = queue.Queue(
            maxsize=self.SEND_QUEUE_SIZE
        )
        self._on_bus_error = on_bus_error
        self._max_consecutive_errors = max_consecutive_errors
        self._bus_error: Exception | None = None
        self._error_reported = False
        self._recv_thread = threading.Thread(
            target=self._recv_loop, daemon=True, name="CANFDMessageDispatcher.recv_loop"
        )
        self._send_thread = threading.Thread(
            target=self._send_loop, daemon=True, name="CANFDMessageDispatcher.send_loop"
        )
        self._recv_thread.start()
        self._send_thread.start()

    @property
    def interface(self) -> CANFDBackend:
        """CANFD backend this dispatcher is bound to."""
        return self._interface

    def _handle_bus_error(self, error: Exception) -> None:
        if self._error_reported:
            return
        self._error_reported = True
        self._running = False
        self._bus_error = error
        self._logger.error(f"CANFD bus fatal error, stopping dispatcher: {error}")
        if self._on_bus_error is not None:
            try:
                self._on_bus_error(error)
            except Exception as callback_error:
                self._logger.error(f"Error in on_bus_error callback: {callback_error}")

    def _recv_loop(self) -> None:
        consecutive_errors = 0
        while self._running:
            try:
                messages = self._interface.receive(
                    max_frames=RECEIVE_BATCH_SIZE,
                    timeout_ms=RECEIVE_TIMEOUT_MS,
                )
                consecutive_errors = 0
                for message in messages:
                    self._dispatch(message)
            except Exception as error:
                consecutive_errors += 1
                if consecutive_errors >= self._max_consecutive_errors:
                    self._logger.error(
                        "CANFD receive failed after %d consecutive errors: %s",
                        consecutive_errors,
                        error,
                    )
                    self._handle_bus_error(error)
                    return
                self._logger.warning(
                    "CANFD receive error (%d/%d): %s",
                    consecutive_errors,
                    self._max_consecutive_errors,
                    error,
                )
                time.sleep(_error_backoff_s(consecutive_errors))

    def _dispatch(self, message: CANFDMessage) -> None:
        with self._subscribers_lock:
            subscribers = self._subscribers[:]
            filtered = self._filtered_subscribers[:]
        for callback in subscribers:
            try:
                callback(message)
            except Exception as error:
                self._logger.error("Error in callback: %s", error)
        for predicate, callback in filtered:
            try:
                if predicate(message):
                    callback(message)
            except Exception as error:
                self._logger.error("Error in filtered callback: %s", error)

    def subscribe(self, callback: Callable[[CANFDMessage], None]) -> None:
        """Register a callback to receive every CANFD message.

        Equivalent to ``subscribe_filter(lambda _: True, callback)`` but
        skips the per-message predicate call.
        """
        with self._subscribers_lock:
            if callback not in self._subscribers:
                self._subscribers.append(callback)

    def subscribe_filter(
        self,
        predicate: Callable[[CANFDMessage], bool],
        callback: Callable[[CANFDMessage], None],
    ) -> None:
        """Register a callback gated by a per-message predicate.

        ``callback`` is invoked only when ``predicate(message)`` returns
        ``True``. Predicates are evaluated by the receive thread, so they
        must be cheap and non-blocking. The L30 client uses this to filter
        by ``(dst_id, src_id)`` before doing the full frame parse, which
        keeps multi-hand dispatch O(1) per hand instead of O(N).
        """
        with self._subscribers_lock:
            entry = (predicate, callback)
            if entry not in self._filtered_subscribers:
                self._filtered_subscribers.append(entry)

    def unsubscribe(self, callback: Callable[[CANFDMessage], None]) -> None:
        """Unregister a CANFD message callback (either plain or filtered)."""
        with self._subscribers_lock:
            if callback in self._subscribers:
                self._subscribers.remove(callback)
            self._filtered_subscribers = [
                (predicate, existing)
                for predicate, existing in self._filtered_subscribers
                if existing is not callback
            ]

    def _send_loop(self) -> None:
        consecutive_errors = 0
        # Detect the optional batch path once; backends that don't implement
        # send_batch fall back to per-frame send transparently.
        send_batch = getattr(self._interface, "send_batch", None)
        while self._running:
            try:
                first = self._send_queue.get(timeout=SEND_QUEUE_GET_TIMEOUT_S)
            except queue.Empty:
                continue
            # Opportunistic batching: drain whatever frames are already queued
            # up to SEND_BATCH_MAX, but never block — if there's only one
            # frame ready, send it immediately rather than introducing latency
            # by waiting for more.
            batch: list[CANFDMessage] = [first]
            if send_batch is not None and self.SEND_BATCH_MAX > 1:
                while len(batch) < self.SEND_BATCH_MAX:
                    try:
                        batch.append(self._send_queue.get_nowait())
                    except queue.Empty:
                        break
            try:
                if send_batch is not None and len(batch) > 1:
                    send_batch(batch)
                else:
                    # Either backend lacks batch support, or only one frame
                    # was ready — both paths fall through to per-frame send.
                    for message in batch:
                        self._interface.send(message)
                consecutive_errors = 0
                # Optional pacing for backward compatibility; default 0 means
                # rely entirely on the vendor USB stack. A previous version
                # spun `while time.monotonic() < deadline: pass` here which
                # pegged one CPU core and capped throughput at ~3300 frames/s.
                if self.SEND_INTERVAL_S > 0:
                    time.sleep(self.SEND_INTERVAL_S)
            except Exception as error:
                consecutive_errors += 1
                if consecutive_errors >= self._max_consecutive_errors:
                    self._logger.error(
                        "CANFD send failed after %d consecutive errors: %s",
                        consecutive_errors,
                        error,
                    )
                    self._handle_bus_error(error)
                    return
                self._logger.warning(
                    "CANFD send error (%d/%d): %s",
                    consecutive_errors,
                    self._max_consecutive_errors,
                    error,
                )
                time.sleep(_error_backoff_s(consecutive_errors))

    def send(self, message: CANFDMessage) -> None:
        """Enqueue a CANFD message for rate-limited transmission."""
        if self._bus_error is not None:
            raise CANError(f"CANFD bus unavailable: {self._bus_error}")
        if not self._running:
            raise RuntimeError("Cannot send on a stopped CANFDMessageDispatcher")
        self._send_queue.put_nowait(message)

    def stop(self) -> None:
        """Stop dispatcher threads and close the CANFD interface.

        Strict ordering to honour the interface's close contract:

        1. Flip ``_error_reported`` and ``_running`` so both worker threads
           observe the shutdown signal on their next iteration.
        2. Join send_thread first (it polls the queue at 10 ms granularity).
        3. Join recv_thread (worst case ~10 ms for vendor receive timeout).
        4. Only then call ``interface.close()`` — by now no worker thread is
           touching the vendor library, so close()'s drain step is uncontended.
        5. Clear subscribers under their own lock.

        If ``stop()`` is invoked from inside a dispatcher-managed callback,
        the calling thread is skipped to avoid join-self deadlock.
        """
        self._error_reported = True
        self._running = False
        current = threading.current_thread()
        for thread in (self._send_thread, self._recv_thread):
            if thread is current:
                continue
            if thread.is_alive():
                thread.join(timeout=THREAD_JOIN_TIMEOUT_S)
                if thread.is_alive():
                    self._logger.warning(
                        "%s did not stop within %.1fs",
                        thread.name,
                        THREAD_JOIN_TIMEOUT_S,
                    )
                    return
        try:
            self._interface.close()
        except Exception as error:
            # Surface as warning rather than swallow silently; the SDK has
            # already accepted the shutdown so we don't propagate the error.
            self._logger.warning("CANFD interface close failed: %s", error)
        with self._subscribers_lock:
            self._subscribers.clear()
            self._filtered_subscribers.clear()

    def __enter__(self) -> "CANFDMessageDispatcher":
        """Enter the context manager."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit the context manager and stop the dispatcher."""
        self.stop()


def _error_backoff_s(consecutive_errors: int) -> float:
    return min(ERROR_BACKOFF_BASE_S * consecutive_errors, ERROR_BACKOFF_MAX_S)
