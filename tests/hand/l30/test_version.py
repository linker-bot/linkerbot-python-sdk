from __future__ import annotations

import threading

import pytest

from linkerbot import L30
from linkerbot.comm.canfd import CANFDMessage
from linkerbot.hand.l30.client import L30Client
from linkerbot.hand.l30.protocol import ProtocolError
from linkerbot.hand.l30.version import L30HandSide, L30Version, VersionManager
from tests.hand.l30.fakes import FakeDispatcher

pytestmark = [pytest.mark.l30, pytest.mark.canfd]


def test_get_device_info_decodes_l30_config_payload() -> None:
    dispatcher = FakeDispatcher()
    version = VersionManager(L30Client(dispatcher, node_id=1, host_id=0))
    result = []

    thread = threading.Thread(target=lambda: result.append(version.get_device_info()))
    thread.start()
    _wait_for_sent(dispatcher, 1)
    _response(dispatcher, 0x00604008, _device_info_response(hand_type=0))
    thread.join(timeout=1)

    assert not thread.is_alive()
    assert dispatcher.sent[0].arbitration_id == 0x00604100
    assert result[0].product_id == 0x13
    assert result[0].serial_number == 1
    assert result[0].software_version == L30Version(1, 0, 6)
    assert result[0].hardware_version == L30Version(0, 0, 3)
    assert result[0].structure_version == L30Version(1, 0, 2)
    assert result[0].node_id == 1
    assert result[0].hand_side is L30HandSide.LEFT
    assert result[0].sensor_type == "B"
    assert result[0].origin == "A"
    assert str(result[0].software_version) == "V1.0.6"


def test_get_product_code_decodes_ascii_payload() -> None:
    dispatcher = FakeDispatcher()
    version = VersionManager(L30Client(dispatcher, node_id=1, host_id=0))
    result: list[str] = []

    thread = threading.Thread(target=lambda: result.append(version.get_product_code()))
    thread.start()
    _wait_for_sent(dispatcher, 1)
    payload = b"LHT30-06-001-L-B-3-A"
    _response(dispatcher, 0x00606008, bytes([len(payload), 0x00, 0x00]) + payload)
    thread.join(timeout=1)

    assert not thread.is_alive()
    assert dispatcher.sent[0].arbitration_id == 0x00606100
    assert result[0] == "LHT30-06-001-L-B-3-A"


def test_get_node_id_decodes_one_byte_payload() -> None:
    dispatcher = FakeDispatcher()
    version = VersionManager(L30Client(dispatcher, node_id=1, host_id=0))
    result: list[int] = []

    thread = threading.Thread(target=lambda: result.append(version.get_node_id()))
    thread.start()
    _wait_for_sent(dispatcher, 1)
    _response(dispatcher, 0x00608008, bytes([1, 0x00, 0x00, 5]))
    thread.join(timeout=1)

    assert not thread.is_alive()
    assert dispatcher.sent[0].arbitration_id == 0x00608100
    assert result[0] == 5


@pytest.mark.parametrize(
    ("raw_value", "side"),
    [(0, L30HandSide.LEFT), (1, L30HandSide.RIGHT)],
)
def test_get_hand_side_decodes_left_and_right(
    raw_value: int, side: L30HandSide
) -> None:
    dispatcher = FakeDispatcher()
    version = VersionManager(L30Client(dispatcher, node_id=1, host_id=0))
    result: list[L30HandSide] = []

    thread = threading.Thread(target=lambda: result.append(version.get_hand_side()))
    thread.start()
    _wait_for_sent(dispatcher, 1)
    _response(dispatcher, 0x0060C008, bytes([1, 0x00, 0x00, raw_value]))
    thread.join(timeout=1)

    assert not thread.is_alive()
    assert dispatcher.sent[0].arbitration_id == 0x0060C100
    assert result[0] is side


def test_get_hand_side_rejects_unknown_value() -> None:
    dispatcher = FakeDispatcher()
    version = VersionManager(L30Client(dispatcher, node_id=1, host_id=0))
    errors: list[Exception] = []

    thread = threading.Thread(
        target=lambda: _capture_error(version.get_hand_side, errors)
    )
    thread.start()
    _wait_for_sent(dispatcher, 1)
    _response(dispatcher, 0x0060C008, bytes([1, 0x00, 0x00, 2]))
    thread.join(timeout=1)

    assert isinstance(errors[0], ProtocolError)


def test_l30_exposes_version_manager() -> None:
    hand = L30(dispatcher=FakeDispatcher(), auto_start_periodic=False)

    assert isinstance(hand.version, VersionManager)

    hand.close()


def _device_info_response(*, hand_type: int) -> bytes:
    payload = bytes(
        [
            0x13,
            0x00,
            0x00,
            0x00,
            0x01,
            0x01,
            0x00,
            0x06,
            0x00,
            0x00,
            0x03,
            0x01,
            0x00,
            0x02,
            0x01,
            hand_type,
            ord("B"),
            ord("A"),
        ]
    )
    return bytes([len(payload), 0x00, 0x00]) + payload


def _response(dispatcher: FakeDispatcher, arbitration_id: int, data: bytes) -> None:
    dispatcher.inject(CANFDMessage(arbitration_id=arbitration_id, data=data))


def _wait_for_sent(dispatcher: FakeDispatcher, count: int) -> None:
    while len(dispatcher.sent) < count:
        pass


def _capture_error(callback, errors: list[Exception]) -> None:
    try:
        callback()
    except Exception as error:
        errors.append(error)
