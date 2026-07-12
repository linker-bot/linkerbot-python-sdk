from __future__ import annotations

import threading
import time

import pytest

import linkerbot
from linkerbot.exceptions import StateError, ValidationError
from linkerbot.hand.o30i import AngleEvent, O30i, SensorSource, protocol
from tests.hand.o30i.fakes import FakeO30iDispatcher

pytestmark = [pytest.mark.o30i, pytest.mark.canfd]


def test_o30i_is_lazily_exported_at_package_and_top_level() -> None:
    from linkerbot.hand import O30i as HandO30i

    assert linkerbot.O30i is O30i
    assert HandO30i is O30i


def test_o30i_defaults_match_measured_standard_can_endpoint() -> None:
    dispatcher = FakeO30iDispatcher()

    with O30i(dispatcher=dispatcher) as hand:
        assert hand.request_id == 0x001
        assert hand.response_id == 0x401
        hand.angle.set_raw_angles([0x80] * 20)

    assert all(message.arbitration_id == 0x001 for message in dispatcher.sent)
    assert all(message.is_extended_id is False for message in dispatcher.sent)
    assert all(message.frame_type == 0x04 for message in dispatcher.sent)
    assert [message.data for message in dispatcher.sent] == [
        bytes.fromhex("01 00 01 80"),
        bytes.fromhex("01 05 0A") + b"\x80" * 10,
        bytes.fromhex("01 10 09") + b"\x80" * 9,
    ]


def test_o30i_supports_custom_standard_request_response_ids() -> None:
    dispatcher = FakeO30iDispatcher(response_id=0x456)

    with O30i(
        request_id=0x123,
        response_id=0x456,
        dispatcher=dispatcher,
    ) as hand:
        hand.speed.set_all(1)

    assert dispatcher.sent[0].arbitration_id == 0x123


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"request_id": True}, "request_id must be int"),
        ({"request_id": 0x400}, "between 0 and 1023"),
        ({"request_id": 0x800, "response_id": 1}, "11-bit"),
        ({"request_id": 1, "response_id": 1}, "must be different"),
        ({"frame_type": True}, "frame_type must be int"),
        ({"frame_type": 256}, "between 0 and 255"),
        ({"device": True}, "device must be int"),
        ({"channel": -1}, "channel must be non-negative"),
    ],
)
def test_o30i_validates_endpoints_before_opening_backend(
    monkeypatch: pytest.MonkeyPatch,
    kwargs: dict[str, object],
    message: str,
) -> None:
    opened = False

    def fail_if_opened(**dispatcher_kwargs):
        nonlocal opened
        opened = True
        raise AssertionError("backend must not open")

    import linkerbot.hand.o30i.o30i as o30i_module

    monkeypatch.setattr(o30i_module, "CANFDMessageDispatcher", fail_if_opened)
    with pytest.raises(ValidationError, match=message):
        O30i(**kwargs)  # type: ignore[arg-type]
    assert opened is False


def test_socketcan_requires_channel() -> None:
    with pytest.raises(ValidationError, match="socketcan_channel"):
        O30i(interface_type="socketcan")


def test_socketcan_routes_all_link_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_backend: dict[str, object] = {}
    captured_dispatcher: dict[str, object] = {}

    class StubBackend:
        def __init__(self, **kwargs: object) -> None:
            captured_backend.update(kwargs)

    class StubDispatcher(FakeO30iDispatcher):
        def __init__(self, **kwargs: object) -> None:
            super().__init__()
            captured_dispatcher.update(kwargs)

    import linkerbot.hand.o30i.o30i as o30i_module

    monkeypatch.setattr(o30i_module, "SocketCANFDBackend", StubBackend)
    monkeypatch.setattr(o30i_module, "CANFDMessageDispatcher", StubDispatcher)

    with O30i(
        interface_type="socketcan",
        socketcan_channel="can7",
        bitrate=2_000_000,
        data_bitrate=4_000_000,
        auto_reconfigure=True,
    ) as hand:
        assert hand.is_closed() is False

    assert captured_backend == {
        "channel": "can7",
        "bitrate": 2_000_000,
        "data_bitrate": 4_000_000,
        "auto_reconfigure": True,
    }
    assert isinstance(captured_dispatcher["interface"], StubBackend)
    assert callable(captured_dispatcher["on_bus_error"])


def test_ctypes_routes_vendor_adapter_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class StubDispatcher(FakeO30iDispatcher):
        def __init__(self, **kwargs: object) -> None:
            super().__init__()
            captured.update(kwargs)

    import linkerbot.hand.o30i.o30i as o30i_module

    monkeypatch.setattr(o30i_module, "CANFDMessageDispatcher", StubDispatcher)

    with O30i(device=2, channel=3, library_path="/tmp/libcanbus.so"):
        pass

    assert captured["device_index"] == 2
    assert captured["channel_index"] == 3
    assert str(captured["library_path"]) == "/tmp/libcanbus.so"
    assert callable(captured["on_bus_error"])


def test_external_dispatcher_is_unsubscribed_but_not_stopped() -> None:
    dispatcher = FakeO30iDispatcher()
    hand = O30i(dispatcher=dispatcher)
    assert len(dispatcher.filtered_subscribers) == 1

    hand.close()
    hand.close()

    assert hand.is_closed() is True
    assert dispatcher.filtered_subscribers == []
    assert dispatcher.stopped is False
    with pytest.raises(StateError):
        hand.protocol.read(main_index=1, length=1)


def test_owned_dispatcher_is_stopped_if_protocol_construction_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[FakeO30iDispatcher] = []

    class StubDispatcher(FakeO30iDispatcher):
        def __init__(self, **kwargs: object) -> None:
            super().__init__()
            created.append(self)

    def fail_protocol(*args: object, **kwargs: object) -> None:
        raise RuntimeError("simulated HandProtocol failure")

    import linkerbot.hand.o30i.o30i as o30i_module

    monkeypatch.setattr(o30i_module, "CANFDMessageDispatcher", StubDispatcher)
    monkeypatch.setattr(o30i_module, "HandProtocolV1", fail_protocol)

    with pytest.raises(RuntimeError, match="HandProtocol failure"):
        O30i()

    assert len(created) == 1
    assert created[0].stopped is True


def test_snapshot_and_stream_receive_blocking_angle_read() -> None:
    dispatcher = FakeO30iDispatcher({protocol.O30I_MI_POSITION: bytes(range(36))})

    with O30i(dispatcher=dispatcher) as hand:
        assert hand.get_snapshot().angle is None
        stream = hand.stream()
        data = hand.angle.get_blocking()
        event = stream.get(timeout=1)
        snapshot = hand.get_snapshot()

    assert isinstance(event, AngleEvent)
    assert event.data is data
    assert snapshot.angle is data


def test_polling_uses_serialized_protocol_reads() -> None:
    dispatcher = FakeO30iDispatcher({protocol.O30I_MI_POSITION: bytes(range(36))})

    with O30i(dispatcher=dispatcher) as hand:
        hand.start_polling({SensorSource.ANGLE: 0.01})
        deadline = time.monotonic() + 1
        while not dispatcher.sent and time.monotonic() < deadline:
            time.sleep(0.001)
        hand.stop_polling()

    assert dispatcher.sent
    assert dispatcher.sent[0].data == bytes.fromhex("01 00 24")


def test_polling_validation_and_partial_start_rollback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dispatcher = FakeO30iDispatcher(
        {
            protocol.O30I_MI_POSITION: bytes(36),
            protocol.O30I_MI_SPEED: bytes(36),
        }
    )
    with O30i(dispatcher=dispatcher) as hand:
        with pytest.raises(ValidationError, match="positive"):
            hand.start_polling({SensorSource.ANGLE: 0})

        real_thread = threading.Thread
        starts = 0

        class FlakyThread(real_thread):
            def start(self) -> None:
                nonlocal starts
                starts += 1
                if starts == 2:
                    raise RuntimeError("thread.start failed")
                super().start()

        monkeypatch.setattr(threading, "Thread", FlakyThread)
        with pytest.raises(RuntimeError, match="thread.start failed"):
            hand.start_polling({SensorSource.ANGLE: 0.01, SensorSource.SPEED: 0.01})
        assert hand._polling_threads == {}
        assert hand._stop_polling.is_set()


def test_dunder_del_swallows_close_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    hand = O30i(dispatcher=FakeO30iDispatcher())

    def fail_close() -> None:
        raise RuntimeError("simulated close failure")

    monkeypatch.setattr(hand, "close", fail_close)
    hand.__del__()
