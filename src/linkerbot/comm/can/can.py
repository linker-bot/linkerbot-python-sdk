import logging
import threading
from collections.abc import Callable

import can


class CANMessageDispatcher:
    """A thread-safe CAN message dispatcher that manages subscribers and message routing.

    This class provides a publish-subscribe pattern for CAN messages, allowing multiple
    subscribers to receive messages from a CAN bus interface. It runs a background thread
    to continuously receive messages and dispatch them to registered callbacks.

    Attributes:
        _bitrate: CAN bus bitrate in bits per second.
        _bus: CAN bus interface instance.
        _subscribers: List of registered callback functions.
        _subscribers_lock: Lock for thread-safe access to subscribers list.
        _running: Flag indicating if the receive loop is active.
        _recv_thread: Background thread for receiving CAN messages.
        _logger: Logger instance for this dispatcher.
    """

    def __init__(self, interface_name: str, interface_type: str = "socketcan"):
        """Initialize the CAN message dispatcher.

        Args:
            interface_name: Name of the CAN interface (e.g., "can0", "vcan0").
            interface_type: Type of CAN interface backend (default: "socketcan").
        """
        self._bitrate = 100_0000
        self._bus: can.BusABC = can.Bus(
            channel=interface_name, interface=interface_type, bitrate=self._bitrate
        )
        self._subscribers: list[Callable[[can.Message], None]] = []
        self._subscribers_lock = threading.Lock()
        self._running = True
        self._recv_thread: threading.Thread = threading.Thread(
            target=self._recv_loop, daemon=True, name="CANMessageDispatcher.recv_loop"
        )
        self._recv_thread.start()

        self._logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    def _recv_loop(self) -> None:
        """Background thread loop for receiving and dispatching CAN messages.

        Continuously receives messages from the CAN bus and dispatches them to all
        registered subscribers. Handles exceptions in both message reception and
        callback execution.
        """
        while self._running:
            try:
                msg = self._bus.recv(timeout=0.01)
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
                self._logger.error(f"Error receiving CAN message: {e}")
                # Continue running even if recv fails

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

    def send(self, msg: can.Message) -> None:
        """Send a CAN message on the bus.

        Args:
            msg: The CAN message to send.
        """
        self._bus.send(msg)

    def stop(self) -> None:
        """Stop the dispatcher and clean up resources.

        Stops the receive loop, waits for the background thread to finish,
        and shuts down the CAN bus interface.
        """
        self._running = False
        if self._recv_thread.is_alive():
            self._recv_thread.join(timeout=1.0)
        self._bus.shutdown()

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
