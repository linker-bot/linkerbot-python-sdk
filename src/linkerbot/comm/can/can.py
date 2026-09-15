import logging
import queue
import threading
import time
from collections.abc import Callable

import can

from linkerbot.exceptions import CANError, ValidationError

from .types import CanInterface

DEFAULT_MAX_CONSECUTIVE_ERRORS = 10
ERROR_BACKOFF_BASE_S = 0.005
ERROR_BACKOFF_MAX_S = 0.05
THREAD_JOIN_TIMEOUT_S = 1.0


class CANMessageDispatcher:
    """A thread-safe CAN message dispatcher that manages subscribers and message routing.

    This class provides a publish-subscribe pattern for CAN messages, allowing multiple
    subscribers to receive messages from a CAN bus interface. It runs a background thread
    to continuously receive messages and dispatch them to registered callbacks.
    """

    SEND_QUEUE_SIZE = 2000
    SEND_INTERVAL_S = 0.0003
    SEND_TIMEOUT_S = 0.1

    def __init__(
        self,
        interface_name: str,
        interface_type: str = "socketcan",
        on_bus_error: Callable[[Exception], None] | None = None,
        max_consecutive_errors: int = DEFAULT_MAX_CONSECUTIVE_ERRORS,
    ) -> None:
        """Initialize the CAN message dispatcher.

        Args:
            interface_name: Name of the CAN interface (e.g., "can0", "vcan0").
            interface_type: Type of CAN interface backend (default: "socketcan").
            on_bus_error: Optional callback invoked once when the bus becomes unavailable.
            max_consecutive_errors: Number of consecutive errors before declaring bus dead.
        """
        if (
            not isinstance(max_consecutive_errors, int)
            or isinstance(max_consecutive_errors, bool)
            or max_consecutive_errors <= 0
        ):
            raise ValidationError("max_consecutive_errors must be a positive int")

        self._can_interface = CanInterface(
            interface_name=interface_name, interface_type=interface_type
        )
        self._bitrate = 1_000_000
        self._bus: can.BusABC = can.Bus(
            channel=interface_name, interface=interface_type, bitrate=self._bitrate
        )
        self._subscribers: list[Callable[[can.Message], None]] = []
        self._subscribers_lock = threading.Lock()
        self._running = True
        self._logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self._send_queue: queue.Queue[can.Message] = queue.Queue(
            maxsize=self.SEND_QUEUE_SIZE
        )
        self._on_bus_error = on_bus_error
        self._max_consecutive_errors = max_consecutive_errors
        self._bus_error: Exception | None = None
        self._error_reported = False
        self._error_lock = threading.Lock()
        self._shutdown_lock = threading.Lock()
        self._shutdown_complete = False
        self._recv_thread: threading.Thread = threading.Thread(
            target=self._recv_loop, daemon=True, name="CANMessageDispatcher.recv_loop"
        )
        self._send_thread: threading.Thread = threading.Thread(
            target=self._send_loop, daemon=True, name="CANMessageDispatcher.send_loop"
        )
        self._recv_thread.start()
        self._send_thread.start()

    @property
    def can_interface(self) -> CanInterface:
        """CAN interface this dispatcher is bound to."""
        return self._can_interface

    def _handle_bus_error(self, error: Exception) -> None:
        """Handle a fatal bus error by stopping the dispatcher and notifying."""
        with self._error_lock:
            if self._error_reported:
                return
            self._error_reported = True
            self._running = False
            self._bus_error = error
        self._logger.error("CAN bus fatal error, stopping dispatcher: %s", error)
        if self._on_bus_error is not None:
            try:
                self._on_bus_error(error)
            except Exception as callback_error:
                self._logger.error("Error in on_bus_error callback: %s", callback_error)

    def _recv_loop(self) -> None:
        """Background thread loop for receiving and dispatching CAN messages.

        Continuously receives messages from the CAN bus and dispatches them to all
        registered subscribers. Handles exceptions in both message reception and
        callback execution.
        """
        consecutive_errors = 0
        while self._running:
            try:
                msg = self._bus.recv(timeout=0.01)
                consecutive_errors = 0
                if not msg:
                    continue
                with self._subscribers_lock:
                    subscribers_copy = self._subscribers[:]
                for callback in subscribers_copy:
                    try:
                        callback(msg)
                    except Exception as error:
                        self._logger.error("Error in callback: %s", error)
            except Exception as error:
                consecutive_errors += 1
                self._logger.warning(
                    "CAN receive error (%d/%d): %s",
                    consecutive_errors,
                    self._max_consecutive_errors,
                    error,
                )
                if consecutive_errors >= self._max_consecutive_errors:
                    self._handle_bus_error(error)
                    return
                time.sleep(_error_backoff_s(consecutive_errors))

    def subscribe(self, callback: Callable[[can.Message], None]) -> None:
        """Register a callback to receive CAN messages.

        Args:
            callback: Function to call when a CAN message is received.
                     Must accept a can.Message parameter.
        """
        with self._subscribers_lock:
            if callback not in self._subscribers:
                self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[can.Message], None]) -> None:
        """Unregister a callback from receiving CAN messages.

        Args:
            callback: The callback function to remove.
        """
        with self._subscribers_lock:
            if callback in self._subscribers:
                self._subscribers.remove(callback)

    def _send_loop(self) -> None:
        """Background thread loop for rate-limited CAN message sending.

        Dequeues messages from the send queue and transmits them at a fixed
        interval of 300 us to avoid flooding the CAN bus.
        """
        consecutive_errors = 0
        while self._running:
            try:
                msg = self._send_queue.get(timeout=0.01)
            except queue.Empty:
                continue
            try:
                deadline = time.monotonic() + self.SEND_INTERVAL_S
                self._bus.send(msg, timeout=self.SEND_TIMEOUT_S)
                consecutive_errors = 0
                remaining = deadline - time.monotonic()
                if remaining > 0:
                    time.sleep(remaining)
            except Exception as error:
                consecutive_errors += 1
                self._logger.warning(
                    "CAN send error (%d/%d): %s",
                    consecutive_errors,
                    self._max_consecutive_errors,
                    error,
                )
                if consecutive_errors >= self._max_consecutive_errors:
                    self._handle_bus_error(error)
                    return

    def send(self, msg: can.Message) -> None:
        """Enqueue a CAN message for rate-limited sending.

        Args:
            msg: The CAN message to send.

        Raises:
            CANError: If the CAN bus is unavailable due to a fatal error.
            RuntimeError: If the dispatcher has been stopped.
            queue.Full: If the send queue is full (2000 messages).
        """
        if self._bus_error is not None:
            raise CANError(f"CAN bus unavailable: {self._bus_error}")
        if not self._running:
            raise RuntimeError("Cannot send on a stopped CANMessageDispatcher")
        self._send_queue.put_nowait(msg)

    def stop(self) -> None:
        """Stop the dispatcher and clean up resources.

        Stops the receive and send loops, waits for background threads to finish,
        and shuts down the CAN bus interface. If a backend ignores the bounded
        send timeout, shutting down the bus is used to interrupt its pending I/O.

        Raises:
            RuntimeError: If a worker remains alive after the bus is shut down.
        """
        with self._error_lock:
            self._error_reported = True
        self._running = False
        current = threading.current_thread()

        running_threads = self._join_worker_threads(current)
        if running_threads:
            self._logger.warning(
                "CAN worker threads did not stop before bus shutdown: %s",
                ", ".join(thread.name for thread in running_threads),
            )

        with self._shutdown_lock:
            if not self._shutdown_complete:
                try:
                    self._bus.shutdown()
                except Exception as error:
                    self._logger.warning("CAN bus shutdown failed: %s", error)
                self._shutdown_complete = True

        running_threads = self._join_worker_threads(current)
        with self._subscribers_lock:
            self._subscribers.clear()
        if running_threads:
            names = ", ".join(thread.name for thread in running_threads)
            raise RuntimeError(
                f"CAN worker threads did not stop after bus shutdown: {names}"
            )

    def _join_worker_threads(self, current: threading.Thread) -> list[threading.Thread]:
        running_threads: list[threading.Thread] = []
        for thread in (self._recv_thread, self._send_thread):
            if thread is current or not thread.is_alive():
                continue
            thread.join(timeout=THREAD_JOIN_TIMEOUT_S)
            if thread.is_alive():
                running_threads.append(thread)
        return running_threads

    def __enter__(self) -> "CANMessageDispatcher":
        """Enter the context manager.

        Returns:
            Self for use in with statements.
        """
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit the context manager and clean up resources.

        Args:
            exc_type: Exception type if an exception occurred.
            exc_val: Exception value if an exception occurred.
            exc_tb: Exception traceback if an exception occurred.
        """
        self.stop()


def _error_backoff_s(consecutive_errors: int) -> float:
    return min(ERROR_BACKOFF_BASE_S * consecutive_errors, ERROR_BACKOFF_MAX_S)
