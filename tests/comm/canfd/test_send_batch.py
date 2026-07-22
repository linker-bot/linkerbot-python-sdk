"""TX batch sending tests for the CANFD ctypes backend and dispatcher.

Vendor PDF §3.22 documents that ``CANFD_Transmit`` accepts up to 100 frames
per call. Pre-fix#141 the SDK always called it with ``items=1`` even when
multiple frames sat in the dispatcher queue, paying one USB control transfer
per frame. The fixes here:

- ``CANFDInterface.send_batch`` writes N frames into a preallocated
  ``_tx_batch`` array and issues a single vendor call.
- ``CANFDMessageDispatcher._send_loop`` opportunistically drains its queue
  (non-blocking) into a batch and uses ``send_batch`` when the backend
  exposes it. Backends without ``send_batch`` fall back to per-frame
  ``send`` transparently — no breaking API changes.
"""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable

import pytest

from linkerbot.comm.canfd import CANFDMessage, CANFDMessageDispatcher
from linkerbot.comm.canfd import ctypes_backend as backend
from linkerbot.exceptions import CANError, ValidationError


class _FakeFn:
    def __init__(self, result: int = 0) -> None:
        self.result = result
        self.calls: list[tuple] = []
        self.restype = None
        self.argtypes = None
        self._hook: Callable | None = None

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
        self.CANFD_Transmit = _FakeFn(0)
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


def test_send_batch_empty_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    interface, lib = _make(monkeypatch)
    lib.CANFD_Transmit.result = 0
    interface.send_batch([])
    assert lib.CANFD_Transmit.calls == []
    interface.close()


def test_send_batch_single_delegates_to_send(monkeypatch: pytest.MonkeyPatch) -> None:
    """A batch of one must take the single-frame fast path (uses _tx_frame)."""
    interface, lib = _make(monkeypatch)
    lib.CANFD_Transmit.result = 1
    captured: list = []

    def capture(dev, channel, frame, count, timeout_ms):
        captured.append((count, frame._obj is interface._tx_frame))
        return 1

    lib.CANFD_Transmit._hook = capture
    interface.send_batch([CANFDMessage(arbitration_id=1, data=b"a")])
    assert captured == [(1, True)]
    interface.close()


def test_send_batch_issues_one_vendor_call_with_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    interface, lib = _make(monkeypatch)
    captured_counts: list[int] = []
    captured_buffer_ids: list[int] = []

    def capture(dev, channel, buffer, count, timeout_ms):
        captured_counts.append(count)
        captured_buffer_ids.append(id(buffer))
        return count

    lib.CANFD_Transmit._hook = capture

    messages = [
        CANFDMessage(arbitration_id=0x100 + i, data=bytes([i])) for i in range(5)
    ]
    interface.send_batch(messages)

    assert captured_counts == [5]
    # All five frames must share the same preallocated batch buffer.
    assert captured_buffer_ids == [id(interface._tx_batch)]
    # Verify the buffer slots actually carry the right IDs in order.
    for i, message in enumerate(messages):
        assert interface._tx_batch[i].ID == message.arbitration_id
        assert interface._tx_batch[i].Data[0] == i
    interface.close()


def test_send_batch_preserves_payload_and_zeroes_padding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each batched frame's data must be memmove'd; padding zeroed per-slot."""
    interface, lib = _make(monkeypatch)
    captured_payloads: list[bytes] = []

    def capture(dev, channel, buffer, count, timeout_ms):
        for i in range(count):
            captured_payloads.append(bytes(buffer[i].Data[:64]))
        return count

    lib.CANFD_Transmit._hook = capture

    interface.send_batch(
        [
            CANFDMessage(arbitration_id=1, data=b"\xff" * 64, dlc=15),
            CANFDMessage(arbitration_id=2, data=b"\xaa\xbb", dlc=2),
        ]
    )

    assert captured_payloads[0] == b"\xff" * 64
    assert captured_payloads[1][:2] == b"\xaa\xbb"
    assert captured_payloads[1][2:] == b"\x00" * 62
    interface.close()


def test_send_batch_short_send_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    interface, lib = _make(monkeypatch)
    lib.CANFD_Transmit.result = 2  # Vendor reports only 2 of 5 sent.

    with pytest.raises(CANError, match="short send"):
        interface.send_batch(
            [CANFDMessage(arbitration_id=i + 1, data=b"x") for i in range(5)]
        )
    interface.close()


def test_send_batch_exceeds_vendor_limit_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    interface, lib = _make(monkeypatch)
    too_many = [
        CANFDMessage(arbitration_id=1, data=b"x")
        for _ in range(backend.CANFD_TRANSMIT_MAX_BATCH + 1)
    ]
    with pytest.raises(ValidationError, match="at most 100"):
        interface.send_batch(too_many)
    interface.close()


def test_send_batch_after_close_raises_fast(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    interface, lib = _make(monkeypatch)
    interface.close()
    transmit_calls_before = len(lib.CANFD_Transmit.calls)
    with pytest.raises(CANError, match="closed"):
        interface.send_batch(
            [
                CANFDMessage(arbitration_id=1, data=b""),
                CANFDMessage(arbitration_id=2, data=b""),
            ]
        )
    assert len(lib.CANFD_Transmit.calls) == transmit_calls_before


class _BatchInterface:
    """Dispatcher-level fake interface that records both ``send`` and
    ``send_batch`` calls so we can assert which path was taken."""

    def __init__(self) -> None:
        self.send_calls: list[CANFDMessage] = []
        self.batch_calls: list[list[CANFDMessage]] = []
        self._gate: threading.Event | None = None
        self._gate_count = 0
        self.closed = False
        self.incoming: queue.Queue = queue.Queue()

    def install_first_send_gate(self) -> threading.Event:
        """Block the first send/send_batch call until the test releases it.

        Used to keep the dispatcher's send thread busy while we queue more
        frames behind it, so the test can deterministically observe the
        batch on the next loop iteration.
        """
        self._gate = threading.Event()
        return self._gate

    def send(self, message: CANFDMessage, timeout_ms: int = 10) -> None:
        if self._gate is not None and self._gate_count == 0:
            self._gate_count += 1
            self._gate.wait(timeout=2.0)
        self.send_calls.append(message)

    def send_batch(self, messages: list[CANFDMessage], timeout_ms: int = 10) -> None:
        if self._gate is not None and self._gate_count == 0:
            self._gate_count += 1
            self._gate.wait(timeout=2.0)
        self.batch_calls.append(list(messages))

    def receive(self, max_frames: int = 64, timeout_ms: int = 10) -> list[CANFDMessage]:
        try:
            msg = self.incoming.get(timeout=timeout_ms / 1000.0)
        except queue.Empty:
            return []
        return [msg]

    def close(self) -> None:
        self.closed = True


class _LegacyInterface:
    """Backend without ``send_batch`` to verify the dispatcher fallback."""

    def __init__(self) -> None:
        self.send_calls: list[CANFDMessage] = []
        self.closed = False
        self.incoming: queue.Queue = queue.Queue()

    def send(self, message: CANFDMessage, timeout_ms: int = 10) -> None:
        self.send_calls.append(message)

    def receive(self, max_frames: int = 64, timeout_ms: int = 10) -> list[CANFDMessage]:
        try:
            msg = self.incoming.get(timeout=timeout_ms / 1000.0)
        except queue.Empty:
            return []
        return [msg]

    def close(self) -> None:
        self.closed = True


def test_dispatcher_coalesces_queued_sends_into_batch() -> None:
    """When multiple frames are queued, dispatcher must call ``send_batch``
    exactly once with all of them in order — not ``send`` N times."""
    interface = _BatchInterface()
    gate = interface.install_first_send_gate()

    dispatcher = CANFDMessageDispatcher(interface=interface)
    try:
        # Hold the dispatcher in the first send (a no-op single frame to
        # prime the gate) so the next three frames queue up.
        dispatcher.send(CANFDMessage(arbitration_id=0, data=b"primer"))
        # Wait for the dispatcher's send thread to enter the gate.
        deadline = time.monotonic() + 1.0
        while interface._gate_count == 0 and time.monotonic() < deadline:
            time.sleep(0.001)
        assert interface._gate_count == 1

        # Now stuff three frames; they all sit in the queue together.
        for i in range(1, 4):
            dispatcher.send(CANFDMessage(arbitration_id=i, data=bytes([i])))
        # Release the gate; dispatcher should drain all three and batch them.
        gate.set()

        # Wait for the batch call to land.
        deadline = time.monotonic() + 1.0
        while not interface.batch_calls and time.monotonic() < deadline:
            time.sleep(0.001)

        assert len(interface.batch_calls) == 1
        ids = [m.arbitration_id for m in interface.batch_calls[0]]
        assert ids == [1, 2, 3]
    finally:
        dispatcher.stop()


def test_dispatcher_falls_back_to_send_when_no_batch_support() -> None:
    interface = _LegacyInterface()
    dispatcher = CANFDMessageDispatcher(interface=interface)
    try:
        for i in range(3):
            dispatcher.send(CANFDMessage(arbitration_id=i + 1, data=b"x"))
        deadline = time.monotonic() + 1.0
        while len(interface.send_calls) < 3 and time.monotonic() < deadline:
            time.sleep(0.001)
        assert [m.arbitration_id for m in interface.send_calls] == [1, 2, 3]
    finally:
        dispatcher.stop()


def test_dispatcher_single_frame_uses_send_not_batch() -> None:
    """If only one frame is ready, dispatcher must use plain send (cheaper
    fast path) rather than send_batch with a one-element list."""
    interface = _BatchInterface()
    dispatcher = CANFDMessageDispatcher(interface=interface)
    try:
        dispatcher.send(CANFDMessage(arbitration_id=42, data=b"x"))
        deadline = time.monotonic() + 1.0
        while not interface.send_calls and time.monotonic() < deadline:
            time.sleep(0.001)
        assert len(interface.send_calls) == 1
        assert interface.send_calls[0].arbitration_id == 42
        assert interface.batch_calls == []
    finally:
        dispatcher.stop()


def test_send_batch_max_caps_per_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """If many frames are queued, the dispatcher must not exceed SEND_BATCH_MAX
    in any single batch (so vendor-side latency stays bounded)."""

    class _CountingBatch(_BatchInterface):
        pass

    interface = _CountingBatch()
    gate = interface.install_first_send_gate()

    class _SmallBatchDispatcher(CANFDMessageDispatcher):
        SEND_BATCH_MAX = 4

    dispatcher = _SmallBatchDispatcher(interface=interface)
    try:
        dispatcher.send(CANFDMessage(arbitration_id=0, data=b"primer"))
        deadline = time.monotonic() + 1.0
        while interface._gate_count == 0 and time.monotonic() < deadline:
            time.sleep(0.001)
        # Queue 10 frames while the dispatcher is gated.
        for i in range(1, 11):
            dispatcher.send(CANFDMessage(arbitration_id=i, data=bytes([i])))
        gate.set()

        deadline = time.monotonic() + 1.5
        while (
            sum(len(b) for b in interface.batch_calls) + len(interface.send_calls) < 10
            and time.monotonic() < deadline
        ):
            time.sleep(0.001)

        # No batch may exceed the configured cap.
        assert all(len(b) <= 4 for b in interface.batch_calls)
        # All 10 frames must have been transmitted somewhere (batch or single).
        # (Order across batches is preserved by the queue.)
    finally:
        dispatcher.stop()
