"""Zero-allocation hot-path tests for the CANFD ctypes backend.

After fix#141 commit 4, send and receive reuse a preallocated ``_tx_frame``
and ``_rx_buffer`` instead of constructing a fresh ``CanFDMsg`` array per
call. These tests pin that behaviour by checking that:

- ``send()`` does NOT instantiate a new ``CanFDMsg`` per call.
- ``receive()`` reuses ``self._rx_buffer`` for requests within the default
  capacity and only allocates when ``max_frames`` exceeds it.
- ``send()`` uses ``ctypes.memmove`` semantics — payload bytes are copied
  verbatim and the tail is zeroed so DLC padding never leaks stale bytes
  from the previous frame.
"""

from __future__ import annotations

import ctypes

import pytest

from linkerbot.comm.canfd import CANFDMessage
from linkerbot.comm.canfd import ctypes_backend as backend


class _FakeFn:
    def __init__(self, result: int = 0) -> None:
        self.result = result
        self.calls: list[tuple] = []
        self.restype = None
        self.argtypes = None
        self._hook = None

    def __call__(self, *args):
        self.calls.append(args)
        if self._hook is not None:
            return self._hook(*args)
        return self.result


class _FakeLib:
    def __init__(self) -> None:
        self._name = "/fake/libcanbus.so"
        self.LibCANbus_Init = _FakeFn(0)
        self.LibCANbus_Exit = _FakeFn(0)
        self.CAN_ScanDevice = _FakeFn(1)
        self.CAN_OpenDevice = _FakeFn(0)
        self.CAN_CloseDevice = _FakeFn(0)
        self.CAN_ReadDevInfo = _FakeFn(0)
        self.CANFD_Init = _FakeFn(0)
        self.CANFD_Transmit = _FakeFn(1)
        self.CANFD_Receive = _FakeFn(0)


@pytest.fixture(autouse=True)
def _reset_lifecycle_state():
    with backend._lifecycle_lock:
        backend._lifecycle_refcount.clear()
        backend._lifecycle_lib.clear()
    yield
    with backend._lifecycle_lock:
        backend._lifecycle_refcount.clear()
        backend._lifecycle_lib.clear()


def _make(monkeypatch: pytest.MonkeyPatch) -> tuple[backend.CANFDInterface, _FakeLib]:
    lib = _FakeLib()
    monkeypatch.setattr(backend, "_load_library", lambda library_path: lib)
    return backend.CANFDInterface(), lib


def test_send_reuses_preallocated_tx_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    interface, lib = _make(monkeypatch)
    tx_frame_id = id(interface._tx_frame)

    for index in range(10):
        interface.send(CANFDMessage(arbitration_id=index, data=b"x"))

    # The preallocated frame is the same object across every send.
    assert id(interface._tx_frame) == tx_frame_id
    # Last frame the vendor saw is the preallocated one.
    last_args = lib.CANFD_Transmit.calls[-1]
    frame_arg = last_args[2]
    # The frame_arg is a byref(self._tx_frame); its _obj points back to the
    # preallocated frame.
    assert frame_arg._obj is interface._tx_frame
    interface.close()


def test_receive_reuses_preallocated_rx_buffer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    interface, lib = _make(monkeypatch)
    rx_buffer_id = id(interface._rx_buffer)

    buffers_seen: list[int] = []

    def capture(dev, channel, buffer, max_frames, timeout_ms):
        buffers_seen.append(id(buffer))
        return 0

    lib.CANFD_Receive._hook = capture

    for _ in range(10):
        interface.receive()

    assert buffers_seen == [rx_buffer_id] * 10
    interface.close()


def test_receive_allocates_when_max_frames_exceeds_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    interface, lib = _make(monkeypatch)
    rx_buffer_id = id(interface._rx_buffer)

    buffers_seen: list[int] = []

    def capture(dev, channel, buffer, max_frames, timeout_ms):
        buffers_seen.append(id(buffer))
        return 0

    lib.CANFD_Receive._hook = capture

    interface.receive(max_frames=backend.CANFD_DEFAULT_MAX_RECEIVE_FRAMES + 1)

    assert buffers_seen[0] != rx_buffer_id
    interface.close()


def test_send_zeroes_dlc_padding_between_frames(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A short frame after a long one must not leak the long frame's tail.

    Reusing ``_tx_frame`` is only safe if every send zeroes the unused
    suffix. Without ``ctypes.memset`` the vendor would read DLC bytes that
    contain leftover application data.
    """
    interface, lib = _make(monkeypatch)
    captured: list[bytes] = []

    def capture(dev, channel, frame, count, timeout_ms):
        # frame is a byref; copy out the full 64-byte data array.
        msg = frame._obj
        captured.append(bytes(msg.Data[:64]))
        return 1

    lib.CANFD_Transmit._hook = capture

    interface.send(
        CANFDMessage(
            arbitration_id=1,
            data=b"\xff" * 64,
            dlc=15,  # DLC 15 = 64 bytes
        )
    )
    interface.send(
        CANFDMessage(
            arbitration_id=2,
            data=b"\x01\x02\x03",
            dlc=3,
        )
    )

    assert captured[0] == b"\xff" * 64
    # Bytes 3..63 of the second frame must be zero, not 0xFF from frame 1.
    assert captured[1][:3] == b"\x01\x02\x03"
    assert captured[1][3:] == b"\x00" * 61
    interface.close()


def test_receive_payload_bytes_match_data_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``string_at``-based payload extraction must match the legacy slice."""
    interface, lib = _make(monkeypatch)

    def fill(dev, channel, buffer, max_frames, timeout_ms):
        frame = buffer[0]
        frame.ID = 0x42
        frame.DLC = 5  # 5 bytes
        frame.ExternFlag = 1
        frame.FrameType = 0x0C
        for index, value in enumerate(b"hello"):
            frame.Data[index] = value
        # leave bytes 5..63 untouched (whatever garbage)
        return 1

    lib.CANFD_Receive._hook = fill

    messages = interface.receive()

    assert len(messages) == 1
    assert messages[0].arbitration_id == 0x42
    assert messages[0].data == b"hello"
    assert messages[0].dlc == 5
    interface.close()


def test_message_to_frame_compat_helper_still_produces_independent_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Legacy helper must not return the preallocated ``_tx_frame``.

    Downstream tooling and tests may call ``_message_to_frame`` directly; the
    new hot path writes into ``self._tx_frame`` but the helper must still
    hand back a stand-alone frame so callers cannot observe later sends
    overwriting their copy.
    """
    interface, _ = _make(monkeypatch)
    frame = interface._message_to_frame(CANFDMessage(arbitration_id=7, data=b"abc"))
    assert frame is not interface._tx_frame
    assert frame.ID == 7
    assert ctypes.string_at(ctypes.addressof(frame.Data), 3) == b"abc"
    interface.close()
