from __future__ import annotations

import threading
import time

import pytest

from linkerbot.comm.canfd import CANFDMessage
from linkerbot.exceptions import StateError, TimeoutError
from linkerbot.hand.o20 import protocol
from linkerbot.hand.o20.client import O20Client
from tests.hand.o20.fakes import FakeDispatcher

pytestmark = [pytest.mark.o20, pytest.mark.canfd]


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
