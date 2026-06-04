from __future__ import annotations

import threading

import numpy as np
import pytest

from linkerbot.comm.canfd import CANFDMessage
from linkerbot.exceptions import StateError, TimeoutError, ValidationError
from linkerbot.hand.l30 import protocol
from linkerbot.hand.l30.angle import AngleManager
from linkerbot.hand.l30.client import L30Client
from linkerbot.hand.l30.control import ControlManager
from linkerbot.hand.l30.current import CurrentManager
from linkerbot.hand.l30.fault import FaultManager
from linkerbot.hand.l30.force_sensor import Finger, ForceSensorManager
from linkerbot.hand.l30.report import ReportManager, ReportSource
from linkerbot.hand.l30.speed import SpeedManager
from linkerbot.hand.l30.temperature import TemperatureManager
from linkerbot.hand.l30.torque import TorqueManager
from tests.hand.l30.fakes import FakeDispatcher

pytestmark = [pytest.mark.l30, pytest.mark.canfd]


def test_control_disable_sends_v2_write_ack_request() -> None:
    dispatcher = FakeDispatcher()
    control = ControlManager(L30Client(dispatcher, node_id=1, host_id=0))

    thread = threading.Thread(target=control.disable)
    thread.start()
    _response(dispatcher, 0x02210008, protocol.ack_payload())
    thread.join(timeout=1)

    assert dispatcher.sent[0].arbitration_id == 0x02210100
    assert dispatcher.sent[0].data == b"\x00\x00"
    assert dispatcher.sent[0].dlc == 0x02


def test_control_nonzero_ack_status_raises_protocol_error() -> None:
    dispatcher = FakeDispatcher()
    control = ControlManager(L30Client(dispatcher, node_id=1, host_id=0))
    errors: list[Exception] = []

    thread = threading.Thread(target=lambda: _capture_error(control.enable, errors))
    thread.start()
    _response(dispatcher, 0x0220E008, protocol.ack_payload(0x20))
    thread.join(timeout=1)

    assert isinstance(errors[0], protocol.ProtocolError)
    assert "0x20" in str(errors[0])


@pytest.mark.parametrize(
    ("manager_factory", "method_name", "values"),
    [
        (AngleManager, "set_angles", [0] * 16),
        (SpeedManager, "set_speeds", [0] * protocol.L30_JOINT_COUNT),
        (TorqueManager, "set_torques", [59] * protocol.L30_JOINT_COUNT),
    ],
)
def test_control_managers_validate_inputs(
    manager_factory, method_name: str, values: list[int]
) -> None:
    manager = manager_factory(L30Client(FakeDispatcher(), node_id=1, host_id=0))

    with pytest.raises(ValidationError):
        getattr(manager, method_name)(values)


@pytest.mark.parametrize(
    ("manager_factory", "method_name"),
    [
        (AngleManager, "get_blocking"),
        (SpeedManager, "get_blocking"),
        (CurrentManager, "get_blocking"),
        (TemperatureManager, "get_blocking"),
        (FaultManager, "get_blocking"),
    ],
)
def test_sensor_managers_validate_blocking_timeout(
    manager_factory, method_name: str
) -> None:
    manager = manager_factory(L30Client(FakeDispatcher(), node_id=1, host_id=0))

    with pytest.raises(ValidationError):
        getattr(manager, method_name)(timeout_ms=0)


def test_report_disable_and_disable_all_send_disable_frames() -> None:
    dispatcher = FakeDispatcher()
    report = ReportManager(L30Client(dispatcher, node_id=1, host_id=0))

    thread = threading.Thread(
        target=lambda: report.configure(ReportSource.SPEED, enabled=True)
    )
    thread.start()
    _response(dispatcher, 0x02806008, protocol.ack_payload())
    thread.join(timeout=1)

    thread = threading.Thread(target=report.disable_all)
    thread.start()
    _response(dispatcher, 0x02806008, protocol.ack_payload())
    thread.join(timeout=1)

    assert dispatcher.sent[0].arbitration_id == 0x02806100
    assert dispatcher.sent[1].arbitration_id == 0x02806100
    assert dispatcher.sent[1].data == bytes.fromhex("09 00 00 00 00 00 00 00 00 00 00")


def test_report_manager_rejects_partial_joint_mask() -> None:
    report = ReportManager(L30Client(FakeDispatcher(), node_id=1, host_id=0))

    with pytest.raises(ValidationError):
        report.configure(ReportSource.ANGLE, joint_mask=0b11)


def test_periodic_reports_update_all_sensor_managers() -> None:
    dispatcher = FakeDispatcher()
    client = L30Client(dispatcher, node_id=1, host_id=0)
    speed = SpeedManager(client)
    current = CurrentManager(client)
    temperature = TemperatureManager(client)
    fault = FaultManager(client)

    _response(dispatcher, 0x00806008, bytes([0x22, 0]) + b"\x00\x03" * 17)
    _response(dispatcher, 0x00804008, bytes([0x22, 0]) + b"\x00\x04" * 17)
    _response(dispatcher, 0x00808008, bytes([0x11, 0]) + bytes(range(17)))
    _response(dispatcher, 0x0080A008, bytes([0x11, 0]) + bytes([0b00101111] * 17))

    assert speed.get_snapshot().speeds == (3,) * 17
    assert current.get_snapshot().currents == (4,) * 17
    assert temperature.get_snapshot().temperatures == tuple(range(17))
    assert fault.get_snapshot().faults == (0b00101111,) * 17
    assert fault.get_snapshot().has_voltage_fault(0)
    assert fault.get_snapshot().has_load_fault(0)


def test_force_sensor_reads_all_fingers_sequentially() -> None:
    dispatcher = FakeDispatcher()
    force_sensor = ForceSensorManager(L30Client(dispatcher, node_id=1, host_id=0))
    result: list = []

    thread = threading.Thread(target=lambda: result.append(force_sensor.get_blocking()))
    thread.start()
    for index, response_id in enumerate(
        [0x00402008, 0x00404008, 0x00406008, 0x00408008, 0x0040A008], start=1
    ):
        _wait_for_sent(dispatcher, index)
        _inject_tactile(dispatcher, response_id)
    thread.join(timeout=1)

    assert [message.arbitration_id for message in dispatcher.sent] == [
        0x00402100,
        0x00404100,
        0x00406100,
        0x00408100,
        0x0040A100,
    ]
    np.testing.assert_array_equal(
        result[0].thumb, np.arange(72, dtype=np.uint8).reshape(12, 6)
    )
    assert force_sensor.get_snapshot() is result[0]


def test_force_sensor_values_are_read_only() -> None:
    dispatcher = FakeDispatcher()
    force_sensor = ForceSensorManager(L30Client(dispatcher, node_id=1, host_id=0))
    result: list = []

    thread = threading.Thread(
        target=lambda: result.append(force_sensor.get_finger(Finger.THUMB))
    )
    thread.start()
    _wait_for_sent(dispatcher, 1)
    _inject_tactile(dispatcher, 0x00402008)
    thread.join(timeout=1)

    with pytest.raises(ValueError):
        result[0].values[0, 0] = 1


def test_force_sensor_status_error_raises_protocol_error() -> None:
    dispatcher = FakeDispatcher()
    force_sensor = ForceSensorManager(L30Client(dispatcher, node_id=1, host_id=0))
    errors: list[Exception] = []

    thread = threading.Thread(
        target=lambda: _capture_error(
            lambda: force_sensor.get_finger(Finger.THUMB), errors
        )
    )
    thread.start()
    dispatcher.inject(
        CANFDMessage(
            arbitration_id=0x00402008, data=bytes([61, 0x10, 0x20]) + bytes(61)
        )
    )
    dispatcher.inject(
        CANFDMessage(arbitration_id=0x00402008, data=bytes([11, 0x11, 0]) + bytes(11))
    )
    thread.join(timeout=1)

    assert isinstance(errors[0], protocol.ProtocolError)


def test_force_sensor_timeout_raises_timeout_error() -> None:
    force_sensor = ForceSensorManager(L30Client(FakeDispatcher(), node_id=1, host_id=0))

    with pytest.raises(TimeoutError):
        force_sensor.get_finger(Finger.THUMB, timeout_ms=1)


def test_client_serializes_same_response_id_requests() -> None:
    dispatcher = FakeDispatcher()
    angle = AngleManager(L30Client(dispatcher, node_id=1, host_id=0))
    results: list[list[int]] = []

    threads = [
        threading.Thread(
            target=lambda: results.append(angle.get_blocking().angles.to_list())
        )
        for _ in range(2)
    ]
    for thread in threads:
        thread.start()

    _wait_for_sent(dispatcher, 1)
    _response(dispatcher, 0x00A02008, _i16_response([1] * protocol.L30_JOINT_COUNT))
    _wait_for_sent(dispatcher, 2)
    _response(dispatcher, 0x00A02008, _i16_response([2] * protocol.L30_JOINT_COUNT))
    for thread in threads:
        thread.join(timeout=1)
        assert not thread.is_alive()

    assert sorted(results) == [
        [1] * protocol.L30_JOINT_COUNT,
        [2] * protocol.L30_JOINT_COUNT,
    ]


def test_client_close_wakes_blocking_read() -> None:
    dispatcher = FakeDispatcher()
    client = L30Client(dispatcher, node_id=1, host_id=0)
    angle = AngleManager(client)
    errors: list[Exception] = []

    thread = threading.Thread(
        target=lambda: _capture_error(
            lambda: angle.get_blocking(timeout_ms=10_000), errors
        )
    )
    thread.start()
    _wait_for_sent(dispatcher, 1)
    client.close()
    thread.join(timeout=1)

    assert not thread.is_alive()
    assert isinstance(errors[0], StateError)


def test_client_close_wakes_tactile_read() -> None:
    dispatcher = FakeDispatcher()
    client = L30Client(dispatcher, node_id=1, host_id=0)
    force_sensor = ForceSensorManager(client)
    errors: list[Exception] = []

    thread = threading.Thread(
        target=lambda: _capture_error(
            lambda: force_sensor.get_finger(Finger.THUMB, timeout_ms=10_000), errors
        )
    )
    thread.start()
    _wait_for_sent(dispatcher, 1)
    client.close()
    thread.join(timeout=1)

    assert not thread.is_alive()
    assert isinstance(errors[0], StateError)


def test_client_ignores_standard_can_frames() -> None:
    dispatcher = FakeDispatcher()
    angle = AngleManager(L30Client(dispatcher, node_id=1, host_id=0))

    dispatcher.inject(
        CANFDMessage(
            arbitration_id=0x200,
            data=bytes([0x22, 0]) + b"\x00\x05" * 17,
            is_extended_id=False,
        )
    )

    assert angle.get_snapshot() is None


def _inject_tactile(dispatcher: FakeDispatcher, arbitration_id: int) -> None:
    dispatcher.inject(
        CANFDMessage(
            arbitration_id=arbitration_id, data=bytes([61, 0x10, 0]) + bytes(range(61))
        )
    )
    dispatcher.inject(
        CANFDMessage(
            arbitration_id=arbitration_id,
            data=bytes([11, 0x11, 0]) + bytes(range(61, 72)),
        )
    )


def _response(dispatcher: FakeDispatcher, arbitration_id: int, data: bytes) -> None:
    dispatcher.inject(CANFDMessage(arbitration_id=arbitration_id, data=data))


def _i16_response(values: list[int]) -> bytes:
    return bytes([0x22, 0x00, 0x00]) + b"".join(
        value.to_bytes(2, "big", signed=True) for value in values
    )


def _wait_for_sent(dispatcher: FakeDispatcher, count: int) -> None:
    while len(dispatcher.sent) < count:
        pass


def _capture_error(callback, errors: list[Exception]) -> None:
    try:
        callback()
    except Exception as error:
        errors.append(error)
