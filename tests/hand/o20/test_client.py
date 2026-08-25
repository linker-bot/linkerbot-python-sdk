from __future__ import annotations

import threading
import time
from concurrent.futures import Future

import pytest

from linkerbot.comm.canfd import CANFDMessage
from linkerbot.exceptions import CANError, StateError, TimeoutError, ValidationError
from linkerbot.hand.o20 import protocol
from linkerbot.hand.o20.client import O20Client
from tests.hand.o20.fakes import FakeDispatcher

pytestmark = [pytest.mark.o20, pytest.mark.canfd]


def test_write_propagates_physical_send_failure() -> None:
    expected = CANError("physical send failed")
    receipt = Future[None]()
    receipt.set_exception(expected)

    class ReceiptDispatcher(FakeDispatcher):
        def send(self, message: CANFDMessage) -> Future[None]:
            super().send(message)
            return receipt

    client = O20Client(ReceiptDispatcher(), device_id=0x01)

    with pytest.raises(CANError) as raised:
        client.write(register=protocol.O20_REG_TARGET_POS, payload=bytes(16))

    assert raised.value is expected


def test_read_only_unblocks_on_write_flag_zero_response() -> None:
    """Write echoes on the same register must not satisfy a pending read.

    Per protocol §5.5, read responses share the same (device_id, register)
    tuple as writes. The client filters by WriteFlag so that an echoed write
    response cannot accidentally hand stale bytes to a concurrent reader.
    """
    dispatcher = FakeDispatcher()
    client = O20Client(dispatcher, device_id=0x01)

    result: list[bytes | str] = []

    def reader() -> None:
        try:
            result.append(
                client.read(register=protocol.O20_REG_CURRENT_POS, timeout_ms=100)
            )
        except TimeoutError:
            result.append("timeout")

    thread = threading.Thread(target=reader)
    thread.start()

    write_echo_id = protocol.build_can_id(
        device_id=0x01, register=protocol.O20_REG_CURRENT_POS, write=True
    )
    dispatcher.inject(CANFDMessage(arbitration_id=write_echo_id, data=b"\xff" * 34))
    thread.join(timeout=1)

    assert result == ["timeout"]


def test_read_unblocks_on_matching_read_response() -> None:
    dispatcher = FakeDispatcher()
    client = O20Client(dispatcher, device_id=0x01)

    result: list[bytes] = []

    def reader() -> None:
        result.append(
            client.read(register=protocol.O20_REG_CURRENT_POS, timeout_ms=200)
        )

    thread = threading.Thread(target=reader)
    thread.start()

    response_id = protocol.build_can_id(
        device_id=0x01, register=protocol.O20_REG_CURRENT_POS, write=False
    )
    payload = bytes([0xAA] * 34)
    dispatcher.inject(CANFDMessage(arbitration_id=response_id, data=payload))
    thread.join(timeout=1)

    assert result[0] == payload


def test_read_ignores_response_for_other_device_id() -> None:
    dispatcher = FakeDispatcher()
    client = O20Client(dispatcher, device_id=0x01)

    result: list[bytes | str] = []

    def reader() -> None:
        try:
            result.append(
                client.read(register=protocol.O20_REG_CURRENT_POS, timeout_ms=100)
            )
        except TimeoutError:
            result.append("timeout")

    thread = threading.Thread(target=reader)
    thread.start()

    foreign_id = protocol.build_can_id(
        device_id=0x02, register=protocol.O20_REG_CURRENT_POS, write=False
    )
    dispatcher.inject(CANFDMessage(arbitration_id=foreign_id, data=bytes(34)))
    thread.join(timeout=1)

    assert result == ["timeout"]


def test_close_wakes_pending_readers_with_state_error() -> None:
    dispatcher = FakeDispatcher()
    client = O20Client(dispatcher, device_id=0x01)

    result: list[Exception] = []

    def reader() -> None:
        try:
            client.read(register=protocol.O20_REG_CURRENT_POS, timeout_ms=5000)
        except Exception as error:
            result.append(error)

    thread = threading.Thread(target=reader)
    thread.start()
    # Give the reader time to register its waiter before closing.
    deadline = time.monotonic() + 1.0
    while not dispatcher.sent and time.monotonic() < deadline:
        time.sleep(0.001)
    assert dispatcher.sent, "reader thread never issued the read request"
    client.close()
    thread.join(timeout=1)

    assert len(result) == 1
    assert isinstance(result[0], StateError)


def test_close_between_frame_build_and_waiter_registration_fails_immediately(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dispatcher = FakeDispatcher()
    client = O20Client(dispatcher, device_id=0x01)
    build_message = client._message

    def close_during_message_build(**kwargs) -> CANFDMessage:
        message = build_message(**kwargs)
        client.close()
        return message

    monkeypatch.setattr(client, "_message", close_during_message_build)

    with pytest.raises(StateError, match="closed"):
        client.read(register=protocol.O20_REG_CURRENT_POS, timeout_ms=1000)

    assert dispatcher.sent == []


def test_close_after_waiter_registration_prevents_send(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dispatcher = FakeDispatcher()
    client = O20Client(dispatcher, device_id=0x01)
    send_message = client._send_message
    waiter_registered = threading.Event()
    release_request = threading.Event()
    close_returned = threading.Event()
    errors: list[Exception] = []

    def pause_before_send(message: CANFDMessage) -> None:
        waiter_registered.set()
        release_request.wait()
        send_message(message)

    def read() -> None:
        try:
            client.read(register=protocol.O20_REG_CURRENT_POS, timeout_ms=1000)
        except Exception as error:
            errors.append(error)

    monkeypatch.setattr(client, "_send_message", pause_before_send)
    request_thread = threading.Thread(target=read)
    request_thread.start()
    assert waiter_registered.wait(timeout=1)
    with client._lock:
        assert client._pending

    close_thread = threading.Thread(
        target=lambda: (client.close(), close_returned.set())
    )
    close_thread.start()
    completed_before_release = close_returned.wait(timeout=1)
    release_request.set()
    close_thread.join(timeout=1)
    request_thread.join(timeout=1)

    assert completed_before_release
    assert not close_thread.is_alive()
    assert not request_thread.is_alive()
    assert len(errors) == 1
    assert isinstance(errors[0], StateError)
    assert dispatcher.sent == []


@pytest.mark.parametrize("timeout_ms", [True, float("nan"), float("inf")])
def test_client_rejects_non_finite_or_boolean_timeout(timeout_ms: float) -> None:
    client = O20Client(FakeDispatcher(), device_id=0x01)

    with pytest.raises(ValidationError):
        client.read(register=protocol.O20_REG_CURRENT_POS, timeout_ms=timeout_ms)


def test_client_uses_subscribe_filter_when_available() -> None:
    """Filter path: O20Client must prefer ``subscribe_filter`` if the
    dispatcher exposes it, so multi-hand buses don't fan out every frame to
    every client just to have each drop non-matching device_ids in Python.
    """
    dispatcher = FakeDispatcher()
    _ = O20Client(dispatcher, device_id=0x01)
    assert len(dispatcher.filtered_subscribers) == 1
    assert dispatcher.subscribers == []

    predicate, _callback = dispatcher.filtered_subscribers[0]
    matching = CANFDMessage(
        arbitration_id=protocol.build_can_id(device_id=0x01, register=0, write=False),
        data=b"",
    )
    non_matching = CANFDMessage(
        arbitration_id=protocol.build_can_id(device_id=0x02, register=0, write=False),
        data=b"",
    )
    assert predicate(matching)
    assert not predicate(non_matching)

    client = O20Client(dispatcher, device_id=0x02)
    assert len(dispatcher.filtered_subscribers) == 2
    client.close()
    assert len(dispatcher.filtered_subscribers) == 1


def test_client_falls_back_to_subscribe_without_filter() -> None:
    """A dispatcher without ``subscribe_filter`` must still receive the
    plain ``subscribe`` registration so legacy or non-CANFDMessageDispatcher
    transports keep working.
    """

    class LegacyDispatcher:
        def __init__(self) -> None:
            self.subscribed: list = []
            self.sent: list = []
            self.stopped = False

        def send(self, message):
            self.sent.append(message)

        def subscribe(self, callback):
            self.subscribed.append(callback)

        def unsubscribe(self, callback):
            if callback in self.subscribed:
                self.subscribed.remove(callback)

        def stop(self) -> None:
            self.stopped = True

    dispatcher = LegacyDispatcher()
    _ = O20Client(dispatcher, device_id=0x01)
    assert len(dispatcher.subscribed) == 1
