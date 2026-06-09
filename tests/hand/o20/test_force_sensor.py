from __future__ import annotations

import numpy as np
import pytest

from linkerbot.exceptions import ValidationError
from linkerbot.hand.o20 import protocol
from linkerbot.hand.o20.client import O20Client
from linkerbot.hand.o20.force_sensor import Finger, ForceSensorManager
from tests.hand.o20.fakes import FakeDispatcher

pytestmark = [pytest.mark.o20, pytest.mark.canfd]


def test_finger_read_assembles_64_plus_9_segments_into_12x6_matrix() -> None:
    data1 = bytes([1]) + bytes(range(63))
    data2 = bytes(range(63, 72))
    dispatcher = FakeDispatcher(
        responses={
            protocol.O20_REG_TACTILE_INDEX_DATA1: data1,
            protocol.O20_REG_TACTILE_INDEX_DATA2: data2,
        }
    )
    client = O20Client(dispatcher, device_id=0x01)
    manager = ForceSensorManager(client)

    result = manager.get_finger(Finger.INDEX).get_blocking(timeout_ms=1000)

    assert result.finger is Finger.INDEX
    assert result.online is True
    np.testing.assert_array_equal(
        result.values, np.arange(72, dtype=np.uint8).reshape(12, 6)
    )


def test_finger_read_propagates_offline_flag() -> None:
    dispatcher = FakeDispatcher(
        responses={
            protocol.O20_REG_TACTILE_THUMB_DATA1: bytes(64),
            protocol.O20_REG_TACTILE_THUMB_DATA2: bytes(9),
        }
    )
    client = O20Client(dispatcher, device_id=0x01)
    manager = ForceSensorManager(client)

    result = manager.get_finger(Finger.THUMB).get_blocking(timeout_ms=1000)

    assert result.online is False
    assert np.all(result.values == 0)


def test_get_blocking_reads_all_five_fingers_and_updates_snapshot() -> None:
    data1 = bytes([1]) + bytes(64 - 1)
    data2 = bytes(9)
    responses = {
        protocol.O20_REG_TACTILE_THUMB_DATA1: data1,
        protocol.O20_REG_TACTILE_THUMB_DATA2: data2,
        protocol.O20_REG_TACTILE_INDEX_DATA1: data1,
        protocol.O20_REG_TACTILE_INDEX_DATA2: data2,
        protocol.O20_REG_TACTILE_MIDDLE_DATA1: data1,
        protocol.O20_REG_TACTILE_MIDDLE_DATA2: data2,
        protocol.O20_REG_TACTILE_RING_DATA1: data1,
        protocol.O20_REG_TACTILE_RING_DATA2: data2,
        protocol.O20_REG_TACTILE_PINKY_DATA1: data1,
        protocol.O20_REG_TACTILE_PINKY_DATA2: data2,
    }
    dispatcher = FakeDispatcher(responses=responses)
    client = O20Client(dispatcher, device_id=0x01)
    manager = ForceSensorManager(client)

    result = manager.get_blocking(timeout_ms=1000)

    assert result.thumb.online is True
    assert result.thumb.values.shape == (12, 6)
    assert result.pinky.values.shape == (12, 6)
    snapshot = manager.get_snapshot()
    assert snapshot is not None
    assert snapshot.timestamp == result.timestamp


def test_force_sensor_rejects_invalid_timeout() -> None:
    manager = ForceSensorManager(O20Client(FakeDispatcher(), device_id=0x01))

    with pytest.raises(ValidationError):
        manager.get_blocking(timeout_ms=0)
