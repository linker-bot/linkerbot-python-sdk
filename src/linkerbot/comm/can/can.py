import logging
import queue
import threading
import time
from collections.abc import Callable

import can

from linkerbot.exceptions import CANError

from .types import CanInterface


class CANMessageDispatcher:
    """A thread-safe CAN message dispatcher that manages subscribers and message routing.

    This class provides a publish-subscribe pattern for CAN messages, allowing multiple
    subscribers to receive messages from a CAN bus interface. It runs a background thread
    to continuously receive messages and dispatch them to registered callbacks.
    """

    SEND_QUEUE_SIZE = 2000
    SEND_INTERVAL_S = 0.0003

    def __init__(
        self,
        interface_name: str,
        interface_type: str = "socketcan",
        on_bus_error: Callable[[Exception], None] | None = None,
        max_consecutive_errors: int = 10,
    ):
        """Initialize the CAN message dispatcher.

        Args:
            interface_name: Name of the CAN interface (e.g., "can0", "vcan0").
            interface_type: Type of CAN interface backend (default: "socketcan").
            on_bus_error: Optional callback invoked once when the bus becomes unavailable.
            max_consecutive_errors: Number of consecutive errors before declaring bus dead.
        """
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
        if self._error_reported:
            return
        self._error_reported = True
        self._running = False
        self._bus_error = error
        self._logger.error(f"CAN bus fatal error, stopping dispatcher: {error}")
        if self._on_bus_error is not None:
            try:
                self._on_bus_error(error)
            except Exception as e:
                self._logger.error(f"Error in on_bus_error callback: {e}")

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
                    except Exception as e:
                        self._logger.error(f"Error in callback: {e}")
            except Exception as e:
                consecutive_errors += 1
                self._logger.error(f"Error receiving CAN message: {e}")
                if consecutive_errors >= self._max_consecutive_errors:
                    self._handle_bus_error(e)
                    return
                time.sleep(min(0.1 * consecutive_errors, 1.0))

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
        interval of 150 us to avoid flooding the CAN bus.
        """
        consecutive_errors = 0
        while self._running:
            try:
                msg = self._send_queue.get(timeout=0.01)
            except queue.Empty:
                continue
            try:
                deadline = time.monotonic() + self.SEND_INTERVAL_S
                self._bus.send(msg)
                consecutive_errors = 0
                # Busy-wait for the remaining interval (time.sleep is too coarse
                # for microsecond precision).
                while time.monotonic() < deadline:
                    pass
            except Exception as e:
                consecutive_errors += 1
                self._logger.error(f"Error sending CAN message: {e}")
                if consecutive_errors >= self._max_consecutive_errors:
                    self._handle_bus_error(e)
                    return

    def send(self, msg: can.Message) -> None:
        """Enqueue a CAN message for rate-limited sending.

        Args:
            msg: The CAN message to send.

        Raises:
            CANError: If the CAN bus is unavailable due to a fatal error.
            RuntimeError: If the dispatcher has been stopped.
            queue.Full: If the send queue is full (1000 messages).
        """
        if self._bus_error is not None:
            raise CANError(f"CAN bus unavailable: {self._bus_error}")
        if not self._running:
            raise RuntimeError("Cannot send on a stopped CANMessageDispatcher")
        self._send_queue.put_nowait(msg)

    def stop(self) -> None:
        """Stop the dispatcher and clean up resources.

        Stops the receive and send loops, waits for background threads to finish,
        and shuts down the CAN bus interface.
        """
        self._error_reported = True
        self._running = False
        current = threading.current_thread()
        for thread in (self._recv_thread, self._send_thread):
            if thread is current:
                continue
            if thread.is_alive():
                thread.join(timeout=1.0)
                if thread.is_alive():
                    self._logger.warning(f"{thread.name} did not stop within timeout")
                    return
        try:
            self._bus.shutdown()
        except Exception:
            pass
        with self._subscribers_lock:
            self._subscribers.clear()

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
