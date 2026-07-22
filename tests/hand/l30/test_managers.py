from __future__ import annotations

import threading

import numpy as np
import pytest

from linkerbot.comm.canfd import CANFDMessage
from linkerbot.hand.l30 import protocol
from linkerbot.hand.l30.angle import AngleManager
from linkerbot.hand.l30.client import L30Client
from linkerbot.hand.l30.control import ControlManager
from linkerbot.hand.l30.current import CurrentManager
from linkerbot.hand.l30.force_sensor import Finger, ForceSensorManager
from linkerbot.hand.l30.report import ReportManager, ReportSource
from linkerbot.hand.l30.speed import SpeedManager
from linkerbot.hand.l30.temperature import TemperatureManager
from linkerbot.hand.l30.torque import TorqueManager
from tests.hand.l30.fakes import FakeDispatcher

pytestmark = [pytest.mark.l30, pytest.mark.canfd]


def test_control_enable_sends_v2_write_ack_request() -> None:
    dispatcher = FakeDispatcher()
    client = L30Client(dispatcher, node_id=1, host_id=0)
    control = ControlManager(client)

    thread = threading.Thread(target=control.enable)
    thread.start()
    _ack(dispatcher, 0x0220E008)
    thread.join(timeout=1)

    assert dispatcher.sent[0].arbitration_id == 0x0220E100
    assert dispatcher.sent[0].data == b"\x00\x00"
    assert dispatcher.sent[0].dlc == 0x02


def test_angle_speed_and_torque_commands_match_vectors() -> None:
    dispatcher = FakeDispatcher()
    client = L30Client(dispatcher, node_id=1, host_id=0)

    AngleManager(client).set_raw_angles([100] * protocol.L30_JOINT_COUNT)
    SpeedManager(client).set_speeds([60] * protocol.L30_JOINT_COUNT)
    TorqueManager(client).set_torques([200] * protocol.L30_JOINT_COUNT)

    angle, speed, torque = dispatcher.sent
    assert angle.arbitration_id == 0x02202100
    assert angle.data == bytes.fromhex("22 00") + b"\x00\x64" * 17
    assert angle.dlc == 0x0E
    assert speed.arbitration_id == 0x02206100
    assert speed.data == bytes.fromhex("22 00") + b"\x00\x3c" * 17
    assert torque.arbitration_id == 0x02204100
    assert torque.data == bytes.fromhex("22 00") + b"\x00\xc8" * 17


def test_angle_read_response_allows_out_of_command_range_sensor_values() -> None:
    dispatcher = FakeDispatcher()
    angle = AngleManager(L30Client(dispatcher, node_id=1, host_id=0))
    values = [0] * protocol.L30_JOINT_COUNT
    values[9] = -1
    result: list = []

    thread = threading.Thread(target=lambda: result.append(angle.get_blocking()))
    thread.start()
    _response(
        dispatcher,
        0x00A02008,
        bytes([0x22, 0x00, 0x00])
        + b"".join(value.to_bytes(2, "big", signed=True) for value in values),
    )
    thread.join(timeout=1)

    snapshot = angle.get_snapshot()
    assert result[0].angles.to_raw() == values
    assert snapshot is not None
    assert snapshot.angles.to_raw() == values


def test_current_temperature_read_responses_update_snapshots() -> None:
    dispatcher = FakeDispatcher()
    client = L30Client(dispatcher, node_id=1, host_id=0)
    current = CurrentManager(client)
    temperature = TemperatureManager(client)

    current_result: list = []
    thread = threading.Thread(
        target=lambda: current_result.append(current.get_blocking())
    )
    thread.start()
    _response(dispatcher, 0x00A04008, bytes([0x22, 0x00, 0x00]) + b"\x00\x02" * 17)
    thread.join(timeout=1)

    temperature_result: list = []
    thread = threading.Thread(
        target=lambda: temperature_result.append(temperature.get_blocking())
    )
    thread.start()
    _response(dispatcher, 0x00A08008, bytes([0x11, 0x00, 0x00]) + bytes(range(17)))
    thread.join(timeout=1)

    current_snapshot = current.get_snapshot()
    temperature_snapshot = temperature.get_snapshot()
    assert current_result[0].currents == (2,) * 17
    assert current_snapshot is not None
    assert current_snapshot.currents == (2,) * 17
    assert temperature_result[0].temperatures == tuple(range(17))
    assert temperature_snapshot is not None
    assert temperature_snapshot.temperatures == tuple(range(17))


def test_report_config_and_active_report_update_angle_snapshot() -> None:
    dispatcher = FakeDispatcher()
    client = L30Client(dispatcher, node_id=1, host_id=0)
    angle = AngleManager(client)
    report = ReportManager(client)

    thread = threading.Thread(
        target=lambda: report.configure(ReportSource.ANGLE, enabled=True, period_ms=20)
    )
    thread.start()
    _ack(dispatcher, 0x02802008)
    thread.join(timeout=1)

    assert dispatcher.sent[0].arbitration_id == 0x02802100
    assert dispatcher.sent[0].data == bytes.fromhex("09 00 01 00 00 00 14 00 00 00 00")
    assert dispatcher.sent[0].dlc == 0x0A

    _response(dispatcher, 0x00802008, bytes([0x22, 0x00]) + b"\x00\x05" * 17)
    snapshot = angle.get_snapshot()
    assert snapshot is not None
    assert snapshot.angles.to_raw() == [5] * 17


def test_force_sensor_assembles_tactile_matrix() -> None:
    dispatcher = FakeDispatcher()
    client = L30Client(dispatcher, node_id=1, host_id=0)
    force_sensor = ForceSensorManager(client)

    result: list = []
    thread = threading.Thread(
        target=lambda: result.append(force_sensor.get_finger(Finger.INDEX))
    )
    thread.start()
    dispatcher.inject(
        CANFDMessage(
            arbitration_id=0x00404008, data=bytes([61, 0x10, 0]) + bytes(range(61))
        )
    )
    dispatcher.inject(
        CANFDMessage(
            arbitration_id=0x00404008, data=bytes([11, 0x11, 0]) + bytes(range(61, 72))
        )
    )
    thread.join(timeout=1)

    assert dispatcher.sent[0].arbitration_id == 0x00404100
    assert result[0].finger is Finger.INDEX
    np.testing.assert_array_equal(
        result[0].values, np.arange(72, dtype=np.uint8).reshape(12, 6)
    )


def _ack(dispatcher: FakeDispatcher, arbitration_id: int) -> None:
    _response(dispatcher, arbitration_id, protocol.ack_payload())


def _response(dispatcher: FakeDispatcher, arbitration_id: int, data: bytes) -> None:
    dispatcher.inject(CANFDMessage(arbitration_id=arbitration_id, data=data))
