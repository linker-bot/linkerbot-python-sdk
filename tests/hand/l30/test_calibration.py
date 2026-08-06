from __future__ import annotations

import pytest

from linkerbot.comm.canfd import CANFDMessage
from linkerbot.exceptions import ValidationError
from linkerbot.hand.l30 import L30, CalibrationManager, ProtocolError, protocol
from tests.hand.l30.fakes import FakeDispatcher

pytestmark = [pytest.mark.l30, pytest.mark.canfd]


class _AutoAckDispatcher(FakeDispatcher):
    def __init__(self, statuses: list[int]) -> None:
        super().__init__()
        self._statuses = iter(statuses)

    def send(self, message: CANFDMessage) -> None:
        super().send(message)
        status = next(self._statuses)
        self.inject(
            CANFDMessage(
                arbitration_id=protocol.expected_response_id(message.arbitration_id),
                data=protocol.ack_payload(status),
                dlc=protocol.L30_ACK_DLC,
            )
        )


def test_calibrate_zero_sends_guarded_protocol_sequence() -> None:
    dispatcher = _AutoAckDispatcher([0x00, 0x00, 0x00])

    with L30(dispatcher=dispatcher, auto_start_periodic=False) as hand:
        assert isinstance(hand.calibration, CalibrationManager)

        hand.calibration.calibrate_zero(confirm=True, timeout_ms=100)

    disable, unlock, calibrate = dispatcher.sent
    assert [message.arbitration_id for message in dispatcher.sent] == [
        0x02210100,
        0x02602100,
        0x0260A100,
    ]
    assert disable.data == bytes.fromhex("00 00")
    assert disable.dlc == 0x02
    assert unlock.data == bytes.fromhex("06 00 12 34 56 78 9A BC")
    assert unlock.dlc == 0x09
    assert calibrate.data == bytes.fromhex("00 00")
    assert calibrate.dlc == 0x02
    assert all(message.frame_type == 0x04 for message in dispatcher.sent)


def test_calibrate_zero_requires_explicit_confirmation_without_sending() -> None:
    dispatcher = _AutoAckDispatcher([])

    with L30(dispatcher=dispatcher, auto_start_periodic=False) as hand:
        with pytest.raises(ValidationError, match="confirm=True"):
            hand.calibration.calibrate_zero()

    assert dispatcher.sent == []


def test_calibrate_zero_validates_timeout_before_sending() -> None:
    dispatcher = _AutoAckDispatcher([])

    with L30(dispatcher=dispatcher, auto_start_periodic=False) as hand:
        with pytest.raises(ValidationError, match="timeout_ms"):
            hand.calibration.calibrate_zero(confirm=True, timeout_ms=0)

    assert dispatcher.sent == []


def test_calibrate_zero_stops_when_disable_fails() -> None:
    dispatcher = _AutoAckDispatcher([0x23])

    with L30(dispatcher=dispatcher, auto_start_periodic=False) as hand:
        with pytest.raises(ProtocolError, match="0x23"):
            hand.calibration.calibrate_zero(confirm=True, timeout_ms=100)

    assert [message.arbitration_id for message in dispatcher.sent] == [0x02210100]


def test_calibrate_zero_stops_when_unlock_fails() -> None:
    dispatcher = _AutoAckDispatcher([0x00, 0x20])

    with L30(dispatcher=dispatcher, auto_start_periodic=False) as hand:
        with pytest.raises(ProtocolError, match="0x20"):
            hand.calibration.calibrate_zero(confirm=True, timeout_ms=100)

    assert [message.arbitration_id for message in dispatcher.sent] == [
        0x02210100,
        0x02602100,
    ]


@pytest.mark.parametrize("status", [0x20, 0x23, 0x31, 0xF0])
def test_calibrate_zero_propagates_calibration_status(status: int) -> None:
    dispatcher = _AutoAckDispatcher([0x00, 0x00, status])

    with L30(dispatcher=dispatcher, auto_start_periodic=False) as hand:
        with pytest.raises(ProtocolError, match=f"0x{status:02X}"):
            hand.calibration.calibrate_zero(confirm=True, timeout_ms=100)

    assert len(dispatcher.sent) == 3
