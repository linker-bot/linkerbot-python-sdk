"""Concurrency model tests for the CANFD ctypes backend.

These tests pin the new lock split introduced in fix#141:

- ``send()`` and ``receive()`` must run truly concurrently — the previous
  single ``_lock`` serialized them, which made the dispatcher's 10 ms
  receive timeout block every transmit. Vendor PDF §4-2 explicitly
  encourages a dedicated long-running receive thread alongside transmits.
- ``close()`` must follow a strict ordering: flip ``_closed_event`` →
  drain ``_tx_lock`` / ``_rx_lock`` → call ``CAN_CloseDevice`` → release
  lifecycle. Skipping the drain would let an in-flight vendor call write
  into a closed USB handle, which is undefined behaviour on the vendor side.
"""

from __future__ import annotations

import threading
import time

import pytest

from linkerbot.comm.canfd import CANFDMessage
from linkerbot.comm.canfd import ctypes_backend as backend
from linkerbot.exceptions import CANError


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


class _SlowReceiveFake:
    """Library fake where CANFD_Receive blocks until released.

    Used to assert that a long-running receive does NOT block send.
    """

    def __init__(self) -> None:
        self._name = "/fake/slow.so"
        self.LibCANbus_Init = _FakeFn(0)
        self.LibCANbus_Exit = _FakeFn(0)
        self.CAN_ScanDevice = _FakeFn(1)
        self.CAN_OpenDevice = _FakeFn(0)
        self.CAN_CloseDevice = _FakeFn(0)
        self.CAN_ReadDevInfo = _FakeFn(0)
        self.CANFD_Init = _FakeFn(0)
        self.CANFD_Transmit = _FakeFn(1)
        self.CANFD_Receive = _FakeFn(0)

        self.recv_entered = threading.Event()
        self.recv_release = threading.Event()
        self.send_observed_during_recv = threading.Event()

        def receive_hook(dev, channel, buffer, max_frames, timeout_ms):
            self.recv_entered.set()
            # Block until the test signals release; in the previous design
            # this would also hold _lock, starving send.
            self.recv_release.wait(timeout=2.0)
            return 0

        def send_hook(dev, channel, frame, count, timeout_ms):
            # If we reach send while receive is still blocked, the lock split
            # worked. Mark it.
            if self.recv_entered.is_set() and not self.recv_release.is_set():
                self.send_observed_during_recv.set()
            return 1

        self.CANFD_Receive._hook = receive_hook
        self.CANFD_Transmit._hook = send_hook


@pytest.fixture(autouse=True)
def _reset_lifecycle_state():
    with backend._lifecycle_lock:
        backend._lifecycle_refcount.clear()
        backend._lifecycle_lib.clear()
    yield
    with backend._lifecycle_lock:
        backend._lifecycle_refcount.clear()
        backend._lifecycle_lib.clear()


def test_send_is_not_blocked_by_a_running_receive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The fix#141 lock split: send must not wait on receive."""
    lib = _SlowReceiveFake()
    monkeypatch.setattr(backend, "_load_library", lambda library_path: lib)
    interface = backend.CANFDInterface()

    def call_receive() -> None:
        try:
            interface.receive(timeout_ms=2000)
        except CANError:
            pass

    recv_thread = threading.Thread(target=call_receive, daemon=True)
    recv_thread.start()
    # Wait for receive to be holding the vendor lock.
    assert lib.recv_entered.wait(timeout=1.0)

    # Now issue a send from the main thread; before the fix, this would
    # block until receive returned. Time-bound to detect regression.
    start = time.monotonic()
    interface.send(CANFDMessage(arbitration_id=1, data=b"x"))
    elapsed = time.monotonic() - start
    assert elapsed < 0.1, f"send blocked for {elapsed:.3f}s while receive was running"
    assert lib.send_observed_during_recv.is_set()

    # Release receive and cleanup.
    lib.recv_release.set()
    recv_thread.join(timeout=2.0)
    interface.close()


def test_close_drains_in_flight_send_before_calling_vendor_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """close() must wait for an in-flight send before CAN_CloseDevice.

    This protects the vendor library from a use-after-close on its USB
    handle. The test holds CANFD_Transmit inside the vendor call, then
    asserts close() blocks until the transmit returns, AND that
    CAN_CloseDevice is invoked only after the transmit has finished.
    """
    lib = _SlowReceiveFake()
    monkeypatch.setattr(backend, "_load_library", lambda library_path: lib)
    interface = backend.CANFDInterface()

    send_inside = threading.Event()
    send_release = threading.Event()
    transmit_finished = threading.Event()

    def slow_send(dev, channel, frame, count, timeout_ms):
        send_inside.set()
        send_release.wait(timeout=2.0)
        transmit_finished.set()
        return 1

    lib.CANFD_Transmit._hook = slow_send

    send_thread = threading.Thread(
        target=lambda: interface.send(CANFDMessage(arbitration_id=1, data=b"x")),
        daemon=True,
    )
    send_thread.start()
    assert send_inside.wait(timeout=1.0)
    # CAN_CloseDevice must not have been called yet.
    assert lib.CAN_CloseDevice.calls == []

    close_done = threading.Event()

    def call_close() -> None:
        interface.close()
        close_done.set()

    close_thread = threading.Thread(target=call_close, daemon=True)
    close_thread.start()

    # close() should block waiting for the in-flight send.
    time.sleep(0.05)
    assert not close_done.is_set(), "close() returned before send drained"
    assert lib.CAN_CloseDevice.calls == [], "CAN_CloseDevice called mid-transmit"

    # Allow send to finish; close should then proceed and call vendor close.
    send_release.set()
    assert transmit_finished.wait(timeout=1.0)
    assert close_done.wait(timeout=1.0)
    assert lib.CAN_CloseDevice.calls == [(0, 0)]

    send_thread.join(timeout=1.0)
    close_thread.join(timeout=1.0)


def test_close_fails_subsequent_calls_fast(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After close, send/receive must raise immediately, not enter vendor."""
    lib = _SlowReceiveFake()
    monkeypatch.setattr(backend, "_load_library", lambda library_path: lib)
    interface = backend.CANFDInterface()

    interface.close()

    transmit_before = len(lib.CANFD_Transmit.calls)
    with pytest.raises(CANError, match="closed"):
        interface.send(CANFDMessage(arbitration_id=1, data=b""))
    with pytest.raises(CANError, match="closed"):
        interface.receive()
    assert len(lib.CANFD_Transmit.calls) == transmit_before


def test_concurrent_sends_serialize_through_tx_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Multiple threads sending must serialize on _tx_lock, not crash."""
    lib = _SlowReceiveFake()
    monkeypatch.setattr(backend, "_load_library", lambda library_path: lib)
    interface = backend.CANFDInterface()
    # Replace transmit with a non-blocking fast path.
    lib.CANFD_Transmit._hook = lambda *args: 1

    errors: list[Exception] = []

    def send_many() -> None:
        try:
            for _ in range(50):
                interface.send(CANFDMessage(arbitration_id=1, data=b"x"))
        except Exception as error:
            errors.append(error)

    threads = [threading.Thread(target=send_many, daemon=True) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5.0)

    assert errors == []
    assert len(lib.CANFD_Transmit.calls) == 200
    interface.close()
