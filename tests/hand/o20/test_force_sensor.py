from __future__ import annotations

import numpy as np
import pytest

from linkerbot.comm.canfd import CANFDMessage
from linkerbot.exceptions import ValidationError
from linkerbot.hand.o20 import protocol
from linkerbot.hand.o20.client import O20Client
from linkerbot.hand.o20.force_sensor import (
    Finger,
    ForceSensorManager,
    O20FingerForceData,
)
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


def test_tactile_transaction_serializes_paired_reads() -> None:
    """Two threads reading tactile data must not interleave their register
    reads, or (data1, data2) can end up cross-sampled from different
    acquisitions and yield a corrupt matrix.

    We inject controllable payloads on the two THUMB registers so that a
    naive interleaving would produce visibly wrong output; the tactile
    transaction lock ensures each thread's data1/data2 pair is atomic.
    """
    import threading

    # Two distinct acquisition rounds. If serialization works, each thread
    # sees a self-consistent (data1, data2) pair from ONE round.
    round_a_data1 = bytes([1]) + b"\x00" * 63  # online=1, all zeros
    round_a_data2 = b"\x00" * 9
    round_b_data1 = bytes([1]) + b"\xff" * 63  # online=1, all 0xFF
    round_b_data2 = b"\xff" * 9

    call_count = {"data1": 0}
    lock = threading.Lock()

    class InterleavingDispatcher(FakeDispatcher):
        def send(self, message):
            self.sent.append(message)
            if not message.is_extended_id:
                return
            try:
                frame_id = protocol.parse_can_id(message.arbitration_id)
            except Exception:
                return
            if frame_id.write != protocol.O20_ACCESS_READ:
                return
            reg = frame_id.register
            if reg == protocol.O20_REG_TACTILE_THUMB_DATA1:
                with lock:
                    call_count["data1"] += 1
                    round_id = call_count["data1"]
                payload = round_a_data1 if round_id == 1 else round_b_data1
            elif reg == protocol.O20_REG_TACTILE_THUMB_DATA2:
                # Match data2 to whichever round the paired data1 belonged to.
                with lock:
                    round_id = call_count["data1"]
                payload = round_a_data2 if round_id == 1 else round_b_data2
            else:
                return
            self.inject(
                CANFDMessage(
                    arbitration_id=protocol.build_can_id(
                        device_id=frame_id.device_id,
                        register=reg,
                        write=False,
                    ),
                    data=payload,
                )
            )

    dispatcher = InterleavingDispatcher()
    client = O20Client(dispatcher, device_id=0x01)
    manager = ForceSensorManager(client)

    results: dict[str, O20FingerForceData] = {}

    def read_thumb(key: str) -> None:
        results[key] = manager.get_finger(Finger.THUMB).get_blocking(timeout_ms=1000)

    threads = [threading.Thread(target=read_thumb, args=(f"t{i}",)) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    # Each thread MUST have gotten a matrix that is either all-zero or
    # all-0xFF. If the tactile lock is missing, one thread would see e.g.
    # data1=round A (zeros) + data2=round B (0xFF) — a mixed matrix.
    for key, result in results.items():
        matrix = result.values
        first_byte = int(matrix.flat[0])
        assert bool((matrix == first_byte).all()), (
            f"{key}: cross-sampled matrix (first={first_byte}, unique="
            f"{sorted(set(matrix.flat))}) — tactile lock is missing"
        )
