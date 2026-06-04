"""Threaded CANFD message dispatcher."""

import logging
import queue
import threading
import time
from collections.abc import Callable
from pathlib import Path

from linkerbot.exceptions import CANError

from .ctypes_backend import CANFDInterface
from .types import CANFDConfigOptions, CANFDMessage

DEFAULT_MAX_CONSECUTIVE_ERRORS = 10
RECEIVE_BATCH_SIZE = 64
RECEIVE_TIMEOUT_MS = 10
SEND_QUEUE_GET_TIMEOUT_S = 0.01
THREAD_JOIN_TIMEOUT_S = 1.0
ERROR_BACKOFF_BASE_S = 0.1
ERROR_BACKOFF_MAX_S = 1.0


class CANFDMessageDispatcher:
    """Thread-safe CANFD dispatcher with publish-subscribe message routing."""

    SEND_QUEUE_SIZE = 2000
    SEND_INTERVAL_S = 0.0003

    def __init__(
        self,
        device_index: int = 0,
        channel_index: int = 0,
        library_path: str | Path | None = None,
        config: CANFDConfigOptions | None = None,
        on_bus_error: Callable[[Exception], None] | None = None,
        max_consecutive_errors: int = DEFAULT_MAX_CONSECUTIVE_ERRORS,
        interface: CANFDInterface | None = None,
    ) -> None:
        """Initialize dispatcher threads for one CANFD interface."""
        self._interface = interface or CANFDInterface(
            device_index=device_index,
            channel_index=channel_index,
            library_path=library_path,
            config=config,
        )
        self._subscribers: list[Callable[[CANFDMessage], None]] = []
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
    def interface(self) -> CANFDInterface:
        """CANFD interface this dispatcher is bound to."""
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
                self._logger.error(f"Error receiving CANFD message: {error}")
                if consecutive_errors >= self._max_consecutive_errors:
                    self._handle_bus_error(error)
                    return
                time.sleep(_error_backoff_s(consecutive_errors))

    def _dispatch(self, message: CANFDMessage) -> None:
        with self._subscribers_lock:
            subscribers = self._subscribers[:]
        for callback in subscribers:
            try:
                callback(message)
            except Exception as error:
                self._logger.error(f"Error in callback: {error}")

    def subscribe(self, callback: Callable[[CANFDMessage], None]) -> None:
        """Register a callback to receive CANFD messages."""
        with self._subscribers_lock:
            if callback not in self._subscribers:
                self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[CANFDMessage], None]) -> None:
        """Unregister a CANFD message callback."""
        with self._subscribers_lock:
            if callback in self._subscribers:
                self._subscribers.remove(callback)

    def _send_loop(self) -> None:
        consecutive_errors = 0
        while self._running:
            try:
                message = self._send_queue.get(timeout=SEND_QUEUE_GET_TIMEOUT_S)
            except queue.Empty:
                continue
            try:
                deadline = time.monotonic() + self.SEND_INTERVAL_S
                self._interface.send(message)
                consecutive_errors = 0
                while time.monotonic() < deadline:
                    pass
            except Exception as error:
                consecutive_errors += 1
                self._logger.error(f"Error sending CANFD message: {error}")
                if consecutive_errors >= self._max_consecutive_errors:
                    self._handle_bus_error(error)
                    return

    def send(self, message: CANFDMessage) -> None:
        """Enqueue a CANFD message for rate-limited transmission."""
        if self._bus_error is not None:
            raise CANError(f"CANFD bus unavailable: {self._bus_error}")
        if not self._running:
            raise RuntimeError("Cannot send on a stopped CANFDMessageDispatcher")
        self._send_queue.put_nowait(message)

    def stop(self) -> None:
        """Stop dispatcher threads and close the CANFD interface."""
        self._error_reported = True
        self._running = False
        current = threading.current_thread()
        for thread in (self._recv_thread, self._send_thread):
            if thread is current:
                continue
            if thread.is_alive():
                thread.join(timeout=THREAD_JOIN_TIMEOUT_S)
                if thread.is_alive():
                    self._logger.warning(f"{thread.name} did not stop within timeout")
                    return
        try:
            self._interface.close()
        except Exception:
            pass
        with self._subscribers_lock:
            self._subscribers.clear()

    def __enter__(self) -> "CANFDMessageDispatcher":
        """Enter the context manager."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit the context manager and stop the dispatcher."""
        self.stop()


def _error_backoff_s(consecutive_errors: int) -> float:
    return min(ERROR_BACKOFF_BASE_S * consecutive_errors, ERROR_BACKOFF_MAX_S)
