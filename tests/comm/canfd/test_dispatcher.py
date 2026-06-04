import queue
import time
from collections.abc import Callable

import pytest

from linkerbot.comm.canfd import CANFDMessage, CANFDMessageDispatcher
from linkerbot.exceptions import CANError


class FakeInterface:
    def __init__(self) -> None:
        self.incoming: queue.Queue[CANFDMessage | Exception] = queue.Queue()
        self.sent: list[CANFDMessage] = []
        self.closed = False
        self.send_error: Exception | None = None
        self.receive_error: Exception | None = None

    def send(self, message: CANFDMessage) -> None:
        if self.send_error is not None:
            raise self.send_error
        self.sent.append(message)

    def receive(self, max_frames: int = 64, timeout_ms: int = 10) -> list[CANFDMessage]:
        if self.receive_error is not None:
            raise self.receive_error
        try:
            item = self.incoming.get(timeout=timeout_ms / 1000)
        except queue.Empty:
            return []
        if isinstance(item, Exception):
            raise item
        return [item]

    def close(self) -> None:
        self.closed = True


def wait_until(predicate: Callable[[], bool], timeout_s: float = 1.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.001)
    raise AssertionError("condition was not met before timeout")


def test_subscriber_receives_incoming_message() -> None:
    interface = FakeInterface()
    dispatcher = CANFDMessageDispatcher(interface=interface)
    received: list[CANFDMessage] = []
    message = CANFDMessage(arbitration_id=1, data=b"abc")

    try:
        dispatcher.subscribe(received.append)
        interface.incoming.put(message)
        wait_until(lambda: received == [message])
    finally:
        dispatcher.stop()


def test_unsubscribe_prevents_future_callbacks() -> None:
    interface = FakeInterface()
    dispatcher = CANFDMessageDispatcher(interface=interface)
    received: list[CANFDMessage] = []
    message = CANFDMessage(arbitration_id=1, data=b"abc")

    try:
        dispatcher.subscribe(received.append)
        dispatcher.unsubscribe(received.append)
        interface.incoming.put(message)
        time.sleep(0.03)
        assert received == []
    finally:
        dispatcher.stop()


def test_send_queues_message_for_fake_interface() -> None:
    interface = FakeInterface()
    dispatcher = CANFDMessageDispatcher(interface=interface)
    message = CANFDMessage(arbitration_id=1, data=b"abc")

    try:
        dispatcher.send(message)
        wait_until(lambda: interface.sent == [message])
    finally:
        dispatcher.stop()


def test_callback_exception_does_not_stop_other_callbacks() -> None:
    interface = FakeInterface()
    dispatcher = CANFDMessageDispatcher(interface=interface)
    received: list[CANFDMessage] = []
    message = CANFDMessage(arbitration_id=1, data=b"abc")

    def broken_callback(message: CANFDMessage) -> None:
        raise RuntimeError("boom")

    try:
        dispatcher.subscribe(broken_callback)
        dispatcher.subscribe(received.append)
        interface.incoming.put(message)
        wait_until(lambda: received == [message])
    finally:
        dispatcher.stop()


def test_receive_errors_trigger_bus_error_once() -> None:
    interface = FakeInterface()
    errors: list[Exception] = []
    dispatcher = CANFDMessageDispatcher(
        interface=interface,
        on_bus_error=errors.append,
        max_consecutive_errors=2,
    )

    try:
        interface.incoming.put(CANError("rx1"))
        interface.incoming.put(CANError("rx2"))
        wait_until(lambda: len(errors) == 1)
        time.sleep(0.03)
        assert len(errors) == 1
    finally:
        dispatcher.stop()


def test_send_errors_trigger_bus_error_once() -> None:
    interface = FakeInterface()
    interface.send_error = CANError("tx")
    errors: list[Exception] = []
    dispatcher = CANFDMessageDispatcher(
        interface=interface,
        on_bus_error=errors.append,
        max_consecutive_errors=1,
    )

    try:
        dispatcher.send(CANFDMessage(arbitration_id=1, data=b""))
        wait_until(lambda: len(errors) == 1)
    finally:
        dispatcher.stop()


def test_send_after_fatal_bus_error_raises_can_error() -> None:
    interface = FakeInterface()
    interface.send_error = CANError("tx")
    dispatcher = CANFDMessageDispatcher(interface=interface, max_consecutive_errors=1)

    try:
        dispatcher.send(CANFDMessage(arbitration_id=1, data=b""))
        wait_until(lambda: not dispatcher._running)
        with pytest.raises(CANError, match="CANFD bus unavailable"):
            dispatcher.send(CANFDMessage(arbitration_id=1, data=b""))
    finally:
        dispatcher.stop()


def test_stop_closes_interface_and_is_idempotent() -> None:
    interface = FakeInterface()
    dispatcher = CANFDMessageDispatcher(interface=interface)

    dispatcher.stop()
    dispatcher.stop()

    assert interface.closed is True


def test_context_manager_stops_dispatcher() -> None:
    interface = FakeInterface()

    with CANFDMessageDispatcher(interface=interface):
        pass

    assert interface.closed is True


def test_send_after_stop_raises_runtime_error() -> None:
    interface = FakeInterface()
    dispatcher = CANFDMessageDispatcher(interface=interface)
    dispatcher.stop()

    with pytest.raises(RuntimeError, match="stopped"):
        dispatcher.send(CANFDMessage(arbitration_id=1, data=b""))
