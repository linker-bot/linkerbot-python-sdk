from __future__ import annotations

import threading

import pytest

from linkerbot.comm.canfd import CANFDMessage
from linkerbot.exceptions import CANError, StateError, ValidationError
from linkerbot.hand.l30 import L30
from linkerbot.hand.l30.events import (
    CurrentEvent,
    FaultEvent,
    SensorSource,
    TemperatureEvent,
)
from linkerbot.hand.l30.protocol import ack_payload
from tests.hand.l30.fakes import FakeDispatcher

pytestmark = [pytest.mark.l30, pytest.mark.canfd]


def test_get_snapshot_includes_all_cached_fields() -> None:
    dispatcher = FakeDispatcher()
    hand = L30(dispatcher=dispatcher, auto_start_periodic=False)

    dispatcher.inject(
        CANFDMessage(
            arbitration_id=0x00802008, data=bytes([0x22, 0]) + b"\x00\x01" * 17
        )
    )
    dispatcher.inject(
        CANFDMessage(
            arbitration_id=0x00806008, data=bytes([0x22, 0]) + b"\x00\x02" * 17
        )
    )
    dispatcher.inject(
        CANFDMessage(
            arbitration_id=0x00804008, data=bytes([0x22, 0]) + b"\x00\x03" * 17
        )
    )
    dispatcher.inject(
        CANFDMessage(
            arbitration_id=0x00808008, data=bytes([0x11, 0]) + bytes(range(17))
        )
    )
    dispatcher.inject(
        CANFDMessage(arbitration_id=0x0080A008, data=bytes([0x11, 0]) + bytes([1] * 17))
    )
    hand.torque.set_all(200)

    snapshot = hand.get_snapshot()

    assert snapshot.angle.angles.to_raw() == [1] * 17
    assert snapshot.speed.speeds == (2,) * 17
    assert snapshot.current.currents == (3,) * 17
    assert snapshot.temperature.temperatures == tuple(range(17))
    assert snapshot.fault.faults == (1,) * 17
    assert snapshot.torque.torques == (200,) * 17
    hand.close()


def test_stream_receives_current_temperature_and_fault_events() -> None:
    dispatcher = FakeDispatcher()
    hand = L30(dispatcher=dispatcher, auto_start_periodic=False)
    stream = hand.stream()

    dispatcher.inject(
        CANFDMessage(
            arbitration_id=0x00804008, data=bytes([0x22, 0]) + b"\x00\x03" * 17
        )
    )
    dispatcher.inject(
        CANFDMessage(
            arbitration_id=0x00808008, data=bytes([0x11, 0]) + bytes(range(17))
        )
    )
    dispatcher.inject(
        CANFDMessage(arbitration_id=0x0080A008, data=bytes([0x11, 0]) + bytes([1] * 17))
    )

    assert isinstance(stream.get(timeout=1), CurrentEvent)
    assert isinstance(stream.get(timeout=1), TemperatureEvent)
    assert isinstance(stream.get(timeout=1), FaultEvent)
    hand.close()


def test_close_stops_owned_dispatcher() -> None:
    dispatcher = FakeDispatcher()
    hand = L30(dispatcher=dispatcher, auto_start_periodic=False)
    hand._owns_dispatcher = True

    hand.close()

    assert dispatcher.stopped


def test_close_after_auto_periodic_disables_reports_not_hardware() -> None:
    dispatcher = FakeDispatcher()
    result: list[L30] = []
    thread = threading.Thread(target=lambda: result.append(L30(dispatcher=dispatcher)))
    thread.start()
    dispatcher.inject(CANFDMessage(arbitration_id=0x02802008, data=ack_payload()))
    thread.join(timeout=1)

    thread = threading.Thread(target=result[0].close)
    thread.start()
    dispatcher.inject(CANFDMessage(arbitration_id=0x02802008, data=ack_payload()))
    thread.join(timeout=1)

    assert [message.arbitration_id for message in dispatcher.sent] == [
        0x02802100,
        0x02802100,
    ]
    assert dispatcher.sent[1].data == bytes.fromhex("09 00 00 00 00 00 00 00 00 00 00")


def test_bus_error_closes_stream_client_and_owned_dispatcher() -> None:
    dispatcher = FakeDispatcher()
    hand = L30(dispatcher=dispatcher, auto_start_periodic=False)
    hand._owns_dispatcher = True
    stream = hand.stream()

    hand._on_bus_error(CANError("bus off"))

    assert hand.is_closed()
    assert dispatcher.stopped
    assert not dispatcher.subscribers
    with pytest.raises(StopIteration):
        stream.get(block=False)
    with pytest.raises(CANError):
        hand.stream()


def test_close_after_client_close_makes_manager_operations_fail() -> None:
    hand = L30(dispatcher=FakeDispatcher(), auto_start_periodic=False)

    hand.close()

    with pytest.raises(StateError):
        hand.angle.set_angles([0] * 17)


@pytest.mark.parametrize("kwargs", [{"node_id": True}, {"device_index": True}])
def test_l30_init_rejects_bool_ids(kwargs) -> None:
    with pytest.raises(ValidationError):
        L30(dispatcher=FakeDispatcher(), auto_start_periodic=False, **kwargs)


def test_start_polling_rejects_force_sensor_invalid_interval() -> None:
    hand = L30(dispatcher=FakeDispatcher(), auto_start_periodic=False)

    with pytest.raises(ValidationError):
        hand.start_polling({SensorSource.FORCE_SENSOR: -1})

    hand.close()


def test_start_polling_rejects_non_sensor_source_key() -> None:
    hand = L30(dispatcher=FakeDispatcher(), auto_start_periodic=False)

    with pytest.raises(ValidationError, match="SensorSource"):
        hand.start_polling({"angle": 0.1})  # type: ignore[arg-type]

    hand.close()
