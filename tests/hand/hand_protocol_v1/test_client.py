from __future__ import annotations

import threading
import time
from collections.abc import Iterable

import pytest

from linkerbot.comm.canfd import CANFDMessage
from linkerbot.exceptions import StateError, TimeoutError, ValidationError
from linkerbot.hand.hand_protocol_v1 import (
    HandProtocolDeviceError,
    HandProtocolError,
    HandProtocolV1,
)
from tests.hand.hand_protocol_v1.fakes import FakeDispatcher

pytestmark = [pytest.mark.o30i, pytest.mark.canfd]


def _response(data: bytes, *, arbitration_id: int = 0x401) -> CANFDMessage:
    return CANFDMessage(
        arbitration_id=arbitration_id,
        data=data,
        is_extended_id=False,
        frame_type=0x04,
    )


def test_read_collects_single_response_and_ignores_padding() -> None:
    def responder(message: CANFDMessage) -> Iterable[CANFDMessage]:
        assert message.data == bytes.fromhex("01 14 05")
        yield _response(bytes.fromhex("01 14 05 01 02 03 04 05") + bytes(40))

    client = HandProtocolV1(FakeDispatcher(responder))

    assert client.read(main_index=1, sub_index=0x14, length=5) == bytes(range(1, 6))


def test_read_assembles_large_object_from_si_fragments() -> None:
    expected = bytes(range(72))

    def responder(message: CANFDMessage) -> Iterable[CANFDMessage]:
        assert message.data == bytes.fromhex("20 00 48")
        yield _response(bytes((0x20, 0x00, 0x3D)) + expected[:61])
        yield _response(bytes((0x20, 0x3D, 0x0B)) + expected[61:])

    client = HandProtocolV1(FakeDispatcher(responder))

    assert client.read(main_index=0x20, length=72) == expected


def test_read_can_assemble_non_overlapping_fragments_out_of_order() -> None:
    expected = bytes(range(72))

    def responder(message: CANFDMessage) -> Iterable[CANFDMessage]:
        yield _response(bytes((0x20, 0x3D, 0x0B)) + expected[61:])
        yield _response(bytes((0x20, 0x00, 0x3D)) + expected[:61])

    client = HandProtocolV1(FakeDispatcher(responder))

    assert client.read(main_index=0x20, length=72) == expected


def test_device_error_response_raises_typed_error() -> None:
    dispatcher = FakeDispatcher(
        lambda message: [_response(bytes.fromhex("4F 28 01 02"))]
    )
    client = HandProtocolV1(dispatcher)

    with pytest.raises(HandProtocolDeviceError) as captured:
        client.read(main_index=0x20, sub_index=0x28, length=10)

    assert captured.value.error_index == 0x28
    assert captured.value.error_code == 0x02


def test_reading_error_object_does_not_treat_it_as_error_response() -> None:
    dispatcher = FakeDispatcher(
        lambda message: [_response(bytes.fromhex("4F 00 01 07"))]
    )
    client = HandProtocolV1(dispatcher)

    assert client.read(main_index=0x4F, length=1) == b"\x07"


def test_write_waits_for_echo_response() -> None:
    def responder(message: CANFDMessage) -> Iterable[CANFDMessage]:
        assert message.data == bytes.fromhex("01 14 05 80 80 80 80 80")
        yield _response(bytes.fromhex("01 14 05 80 80 80 80 80"))

    dispatcher = FakeDispatcher(responder)
    client = HandProtocolV1(dispatcher)

    assert client.write(main_index=1, sub_index=0x14, payload=b"\x80" * 5) == (
        b"\x80" * 5
    )


def test_frames_with_wrong_id_or_extended_flag_do_not_satisfy_request() -> None:
    def responder(message: CANFDMessage) -> Iterable[CANFDMessage]:
        yield _response(bytes.fromhex("01 00 01 AA"), arbitration_id=0x402)
        yield CANFDMessage(
            arbitration_id=0x401,
            data=bytes.fromhex("01 00 01 BB"),
            is_extended_id=True,
        )
        yield _response(bytes.fromhex("01 00 01 CC"))

    client = HandProtocolV1(FakeDispatcher(responder))

    assert client.read(main_index=1, length=1) == b"\xcc"


def test_read_ignores_response_with_wrong_rts_bit() -> None:
    def responder(message: CANFDMessage) -> Iterable[CANFDMessage]:
        yield _response(bytes.fromhex("81 00 01 AA"))
        yield _response(bytes.fromhex("01 00 01 BB"))

    client = HandProtocolV1(FakeDispatcher(responder))

    assert client.read(main_index=1, length=1, rts=False) == b"\xbb"


def test_target_read_ignores_actual_value_response() -> None:
    def responder(message: CANFDMessage) -> Iterable[CANFDMessage]:
        yield _response(bytes.fromhex("01 00 01 AA"))
        yield _response(bytes.fromhex("81 00 01 BB"))

    client = HandProtocolV1(FakeDispatcher(responder))

    assert client.read(main_index=1, length=1, rts=True) == b"\xbb"


def test_malformed_matching_frame_fails_pending_request() -> None:
    dispatcher = FakeDispatcher(lambda message: [_response(b"\x01\x00")])
    client = HandProtocolV1(dispatcher)

    with pytest.raises(Exception, match="header"):
        client.read(main_index=1, length=1)


def test_timeout_and_timeout_validation() -> None:
    client = HandProtocolV1(FakeDispatcher())

    with pytest.raises(TimeoutError):
        client.read(main_index=1, length=1, timeout_ms=5)
    with pytest.raises(ValidationError, match="positive"):
        client.read(main_index=1, length=1, timeout_ms=0)
    with pytest.raises(ValidationError, match="int or float"):
        client.read(main_index=1, length=1, timeout_ms=True)


def test_close_unsubscribes_exact_callback_and_is_idempotent() -> None:
    dispatcher = FakeDispatcher()
    client = HandProtocolV1(dispatcher)
    assert len(dispatcher.filtered_subscribers) == 1

    client.close()
    client.close()

    assert dispatcher.filtered_subscribers == []
    with pytest.raises(StateError):
        client.read(main_index=1, length=1)


def test_close_wakes_pending_request() -> None:
    dispatcher = FakeDispatcher()
    client = HandProtocolV1(dispatcher)
    errors: list[Exception] = []

    def read() -> None:
        try:
            client.read(main_index=1, length=1, timeout_ms=1000)
        except Exception as error:
            errors.append(error)

    thread = threading.Thread(target=read)
    thread.start()
    deadline = time.monotonic() + 0.2
    while not dispatcher.sent and time.monotonic() < deadline:
        time.sleep(0.001)
    client.close()
    thread.join(timeout=1)

    assert len(errors) == 1
    assert isinstance(errors[0], StateError)


def test_conflicting_duplicate_fragment_fails_transaction() -> None:
    def responder(message: CANFDMessage) -> Iterable[CANFDMessage]:
        yield _response(bytes.fromhex("20 00 01 AA"))
        yield _response(bytes.fromhex("20 00 01 BB"))

    client = HandProtocolV1(FakeDispatcher(responder))

    with pytest.raises(HandProtocolError, match="conflicting duplicate"):
        client.read(main_index=0x20, length=2)


def test_concurrent_requests_are_serialized_without_transaction_ids() -> None:
    dispatcher = FakeDispatcher()
    client = HandProtocolV1(dispatcher)
    results: list[bytes] = []

    def read(sub_index: int) -> None:
        results.append(
            client.read(
                main_index=1,
                sub_index=sub_index,
                length=1,
                timeout_ms=1000,
            )
        )

    first = threading.Thread(target=read, args=(0,))
    second = threading.Thread(target=read, args=(1,))
    first.start()
    deadline = time.monotonic() + 1
    while len(dispatcher.sent) < 1 and time.monotonic() < deadline:
        time.sleep(0.001)
    second.start()
    time.sleep(0.01)

    # The second request cannot be sent until the first response completes.
    assert len(dispatcher.sent) == 1
    dispatcher.inject(_response(bytes.fromhex("01 00 01 AA")))
    deadline = time.monotonic() + 1
    while len(dispatcher.sent) < 2 and time.monotonic() < deadline:
        time.sleep(0.001)
    dispatcher.inject(_response(bytes.fromhex("01 01 01 BB")))
    first.join(timeout=1)
    second.join(timeout=1)

    assert results == [b"\xaa", b"\xbb"]
    assert [message.data for message in dispatcher.sent] == [
        bytes.fromhex("01 00 01"),
        bytes.fromhex("01 01 01"),
    ]
