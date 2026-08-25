import queue
import threading
import time
from collections.abc import Callable

import pytest

from linkerbot.comm.canfd import CANFDMessage, CANFDMessageDispatcher
from linkerbot.comm.canfd import dispatcher as dispatcher_module
from linkerbot.exceptions import CANError, StateError, ValidationError


class FakeInterface:
    def __init__(self) -> None:
        self.incoming: queue.Queue[CANFDMessage | Exception] = queue.Queue()
        self.sent: list[CANFDMessage] = []
        self.closed = False
        self.close_calls = 0
        self.send_error: Exception | None = None
        self.receive_error: Exception | None = None

    def send(self, message: CANFDMessage, timeout_ms: int = 10) -> None:
        _ = timeout_ms
        if self.send_error is not None:
            raise self.send_error
        self.sent.append(message)

    def receive(self, max_frames: int = 64, timeout_ms: int = 10) -> list[CANFDMessage]:
        if self.receive_error is not None:
            raise self.receive_error
        try:
            item = self.incoming.get(timeout=timeout_ms / 1000)
        except queue.Empty:
            return []
        if isinstance(item, Exception):
            raise item
        return [item]

    def close(self) -> None:
        self.close_calls += 1
        self.closed = True


def wait_until(predicate: Callable[[], bool], timeout_s: float = 1.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.001)
    raise AssertionError("condition was not met before timeout")


def test_subscriber_receives_incoming_message() -> None:
    interface = FakeInterface()
    dispatcher = CANFDMessageDispatcher(interface=interface)
    received: list[CANFDMessage] = []
    message = CANFDMessage(arbitration_id=1, data=b"abc")

    try:
        dispatcher.subscribe(received.append)
        interface.incoming.put(message)
        wait_until(lambda: received == [message])
    finally:
        dispatcher.stop()


def test_unsubscribe_prevents_future_callbacks() -> None:
    interface = FakeInterface()
    dispatcher = CANFDMessageDispatcher(interface=interface)
    received: list[CANFDMessage] = []
    message = CANFDMessage(arbitration_id=1, data=b"abc")

    try:
        dispatcher.subscribe(received.append)
        dispatcher.unsubscribe(received.append)
        interface.incoming.put(message)
        time.sleep(0.03)
        assert received == []
    finally:
        dispatcher.stop()


def test_send_queues_message_for_fake_interface() -> None:
    interface = FakeInterface()
    dispatcher = CANFDMessageDispatcher(interface=interface)
    message = CANFDMessage(arbitration_id=1, data=b"abc")

    try:
        receipt = dispatcher.send(message)
        assert receipt.cancel() is False
        assert receipt.result(timeout=1.0) is None
        assert interface.sent == [message]
    finally:
        dispatcher.stop()


def test_send_receipt_preserves_background_can_error() -> None:
    interface = FakeInterface()
    expected = CANError("invalid CANFD frame")
    interface.send_error = expected
    dispatcher = CANFDMessageDispatcher(interface=interface)

    try:
        receipt = dispatcher.send(CANFDMessage(arbitration_id=1, data=b"x"))
        with pytest.raises(CANError) as raised:
            receipt.result(timeout=1.0)
        assert raised.value is expected
    finally:
        dispatcher.stop()


def test_send_receipt_wraps_background_system_error() -> None:
    interface = FakeInterface()
    expected = OSError("write failed")
    interface.send_error = expected
    dispatcher = CANFDMessageDispatcher(interface=interface)

    try:
        receipt = dispatcher.send(CANFDMessage(arbitration_id=1, data=b"x"))
        with pytest.raises(CANError, match="background send failed") as raised:
            receipt.result(timeout=1.0)
        assert raised.value.__cause__ is expected
    finally:
        dispatcher.stop()


def test_fatal_send_failure_fails_current_and_queued_receipts() -> None:
    class GatedFailingInterface(FakeInterface):
        def __init__(self) -> None:
            super().__init__()
            self.send_started = threading.Event()
            self.release_send = threading.Event()

        def send(self, message: CANFDMessage, timeout_ms: int = 10) -> None:
            _ = message, timeout_ms
            self.send_started.set()
            assert self.release_send.wait(timeout=1.0)
            raise CANError("physical send failed")

    interface = GatedFailingInterface()
    dispatcher = CANFDMessageDispatcher(interface=interface, max_consecutive_errors=1)
    first = dispatcher.send(CANFDMessage(arbitration_id=1, data=b"a"))
    assert interface.send_started.wait(timeout=1.0)
    second = dispatcher.send(CANFDMessage(arbitration_id=2, data=b"b"))
    third = dispatcher.send(CANFDMessage(arbitration_id=3, data=b"c"))
    interface.release_send.set()

    try:
        for receipt in (first, second, third):
            with pytest.raises(CANError):
                receipt.result(timeout=1.0)
        wait_until(lambda: not dispatcher._running)
    finally:
        dispatcher.stop()


def test_stop_fails_in_flight_and_queued_receipts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BlockingSendInterface(FakeInterface):
        def __init__(self) -> None:
            super().__init__()
            self.send_started = threading.Event()
            self.release_send = threading.Event()

        def send(self, message: CANFDMessage, timeout_ms: int = 10) -> None:
            assert self.release_send.wait(timeout=1.0)
            super().send(message, timeout_ms)

    monkeypatch.setattr(dispatcher_module, "THREAD_JOIN_TIMEOUT_S", 0.01)
    interface = BlockingSendInterface()
    dispatcher = CANFDMessageDispatcher(interface=interface)
    first = dispatcher.send(CANFDMessage(arbitration_id=1, data=b"a"))
    second = dispatcher.send(CANFDMessage(arbitration_id=2, data=b"b"))

    try:
        dispatcher.stop()
        for receipt in (first, second):
            with pytest.raises(StateError, match="stopped before queued send"):
                receipt.result(timeout=0)
    finally:
        interface.release_send.set()
        dispatcher._send_thread.join(timeout=1.0)
        dispatcher.stop()


def test_callback_exception_does_not_stop_other_callbacks() -> None:
    interface = FakeInterface()
    dispatcher = CANFDMessageDispatcher(interface=interface)
    received: list[CANFDMessage] = []
    message = CANFDMessage(arbitration_id=1, data=b"abc")

    def broken_callback(message: CANFDMessage) -> None:
        raise RuntimeError("boom")

    try:
        dispatcher.subscribe(broken_callback)
        dispatcher.subscribe(received.append)
        interface.incoming.put(message)
        wait_until(lambda: received == [message])
    finally:
        dispatcher.stop()


def test_receive_errors_trigger_bus_error_once() -> None:
    interface = FakeInterface()
    errors: list[Exception] = []
    dispatcher = CANFDMessageDispatcher(
        interface=interface,
        on_bus_error=errors.append,
        max_consecutive_errors=2,
    )

    try:
        interface.incoming.put(CANError("rx1"))
        interface.incoming.put(CANError("rx2"))
        wait_until(lambda: len(errors) == 1)
        time.sleep(0.03)
        assert len(errors) == 1
    finally:
        dispatcher.stop()


def test_send_errors_trigger_bus_error_once() -> None:
    interface = FakeInterface()
    interface.send_error = CANError("tx")
    errors: list[Exception] = []
    dispatcher = CANFDMessageDispatcher(
        interface=interface,
        on_bus_error=errors.append,
        max_consecutive_errors=1,
    )

    try:
        dispatcher.send(CANFDMessage(arbitration_id=1, data=b""))
        wait_until(lambda: len(errors) == 1)
    finally:
        dispatcher.stop()


def test_send_after_fatal_bus_error_raises_can_error() -> None:
    interface = FakeInterface()
    interface.send_error = CANError("tx")
    dispatcher = CANFDMessageDispatcher(interface=interface, max_consecutive_errors=1)

    try:
        dispatcher.send(CANFDMessage(arbitration_id=1, data=b""))
        wait_until(lambda: not dispatcher._running)
        with pytest.raises(CANError, match="CANFD bus unavailable"):
            dispatcher.send(CANFDMessage(arbitration_id=1, data=b""))
    finally:
        dispatcher.stop()


def test_stop_closes_interface_and_is_idempotent() -> None:
    interface = FakeInterface()
    dispatcher = CANFDMessageDispatcher(interface=interface)

    dispatcher.stop()
    dispatcher.stop()

    assert interface.closed is True
    assert interface.close_calls == 1


def test_concurrent_fatal_errors_report_only_once() -> None:
    class SlowFalse:
        def __bool__(self) -> bool:
            # Release the GIL between the old check and assignment so both
            # callers would observe false without the fatal-transition lock.
            time.sleep(0.03)
            return False

    interface = FakeInterface()
    errors: list[Exception] = []
    dispatcher = CANFDMessageDispatcher(interface=interface, on_bus_error=errors.append)
    dispatcher._error_reported = SlowFalse()  # ty: ignore[invalid-assignment]
    start = threading.Barrier(3)

    def report_error(message: str) -> None:
        start.wait()
        dispatcher._handle_bus_error(CANError(message))

    threads = [
        threading.Thread(target=report_error, args=(f"error-{index}",))
        for index in range(2)
    ]
    for thread in threads:
        thread.start()
    start.wait()
    for thread in threads:
        thread.join(timeout=1.0)

    try:
        assert all(not thread.is_alive() for thread in threads)
        assert len(errors) == 1
    finally:
        dispatcher.stop()


def test_concurrent_stop_closes_interface_only_once() -> None:
    class SlowCloseInterface(FakeInterface):
        def close(self) -> None:
            time.sleep(0.03)
            super().close()

    interface = SlowCloseInterface()
    dispatcher = CANFDMessageDispatcher(interface=interface)
    start = threading.Barrier(3)

    def stop() -> None:
        start.wait()
        dispatcher.stop()

    threads = [threading.Thread(target=stop) for _ in range(2)]
    for thread in threads:
        thread.start()
    start.wait()
    for thread in threads:
        thread.join(timeout=2.0)

    assert all(not thread.is_alive() for thread in threads)
    assert interface.close_calls == 1


def test_context_manager_stops_dispatcher() -> None:
    interface = FakeInterface()

    with CANFDMessageDispatcher(interface=interface):
        pass

    assert interface.closed is True


@pytest.mark.parametrize("value", [0, -1, True, 1.5])
def test_invalid_error_threshold_is_rejected(value: object) -> None:
    with pytest.raises(ValidationError, match="positive int"):
        CANFDMessageDispatcher(
            interface=FakeInterface(),
            max_consecutive_errors=value,  # ty: ignore[invalid-argument-type]
        )


def test_falsy_backend_is_not_replaced_by_vendor_interface() -> None:
    class FalsyInterface(FakeInterface):
        def __bool__(self) -> bool:
            return False

    interface = FalsyInterface()

    with CANFDMessageDispatcher(interface=interface) as dispatcher:
        assert dispatcher.interface is interface


def test_unsubscribe_removes_fresh_bound_method_from_filtered_subscribers() -> None:
    class Receiver:
        def __init__(self) -> None:
            self.messages: list[CANFDMessage] = []

        def receive(self, message: CANFDMessage) -> None:
            self.messages.append(message)

    interface = FakeInterface()
    receiver = Receiver()
    dispatcher = CANFDMessageDispatcher(interface=interface)
    try:
        dispatcher.subscribe_filter(lambda _: True, receiver.receive)
        # Each attribute access creates a new bound-method object. Unsubscribe
        # must compare callbacks by equality, as plain subscriptions do.
        dispatcher.unsubscribe(receiver.receive)
        dispatcher._dispatch(CANFDMessage(arbitration_id=1, data=b"x"))
        assert receiver.messages == []
    finally:
        dispatcher.stop()


def test_send_after_stop_raises_runtime_error() -> None:
    interface = FakeInterface()
    dispatcher = CANFDMessageDispatcher(interface=interface)
    dispatcher.stop()

    with pytest.raises(RuntimeError, match="stopped"):
        dispatcher.send(CANFDMessage(arbitration_id=1, data=b""))


def test_send_loop_does_not_busy_wait_by_default() -> None:
    """SEND_INTERVAL_S=0 must not spin a CPU between frames.

    Regression guard against the prior `while time.monotonic() < deadline: pass`
    that pegged a core and capped send throughput. We measure CPU time spent
    by the *dispatcher* threads while idle (no work). With busy-wait, CPU time
    rises linearly with wall time; with the fix, it stays near zero.
    """
    import os
    import resource

    interface = FakeInterface()
    dispatcher = CANFDMessageDispatcher(interface=interface)
    try:
        wall_start = time.monotonic()
        cpu_start = (
            resource.getrusage(resource.RUSAGE_SELF).ru_utime
            + resource.getrusage(resource.RUSAGE_SELF).ru_stime
        )
        # Send 100 frames; with busy-wait this would consume ~30 ms of CPU
        # time in spinning. With the fix, idle time dominates.
        message = CANFDMessage(arbitration_id=1, data=b"x")
        for _ in range(100):
            dispatcher.send(message)
        wait_until(lambda: len(interface.sent) == 100, timeout_s=2.0)
        wall_elapsed = time.monotonic() - wall_start
        cpu_elapsed = (
            resource.getrusage(resource.RUSAGE_SELF).ru_utime
            + resource.getrusage(resource.RUSAGE_SELF).ru_stime
        ) - cpu_start
        # CPU/wall ratio caps the fraction of time we're not blocking. On a
        # busy machine the test sometimes sees CPU=wall due to other threads,
        # but the busy-wait bug specifically produced ratios > 0.8 on every
        # run. Allow generous headroom.
        assert cpu_elapsed < max(0.1, wall_elapsed * 0.7), (
            f"dispatcher consumed {cpu_elapsed:.3f}s CPU over {wall_elapsed:.3f}s "
            "wall — busy-wait may have returned"
        )
        _ = os  # keep import used even if unused under future edits
    finally:
        dispatcher.stop()


def test_error_backoff_recovers_within_milliseconds() -> None:
    """Transient receive errors must recover quickly, not pause the bus.

    Previously the backoff scaled 0.1 → 1.0 s and a single hiccup blocked
    receive for hundreds of milliseconds. The redesign tightens this to
    5–50 ms so an L30 user does not observe seconds-long stalls.
    """
    interface = FakeInterface()
    dispatcher = CANFDMessageDispatcher(interface=interface, max_consecutive_errors=5)
    received: list[CANFDMessage] = []
    message = CANFDMessage(arbitration_id=1, data=b"x")
    try:
        dispatcher.subscribe(received.append)
        # Inject one transient error then a real message; with old backoff the
        # message would take >100 ms to surface. New backoff should deliver
        # well under 100 ms even with one error.
        interface.incoming.put(CANError("transient"))
        time.sleep(0.001)
        interface.incoming.put(message)
        wait_until(lambda: received == [message], timeout_s=0.2)
    finally:
        dispatcher.stop()
