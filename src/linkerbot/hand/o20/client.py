"""Transport-neutral O20 protocol client.

The O20 client encodes register read and write requests, sends them through a
dispatcher-like CANFD transport, and routes responses to the request that
issued them. The protocol matches read responses by ``(device_id, register)``;
the WriteFlag bit identifies the frame direction. Only frames with WriteFlag=0
satisfy pending read waiters so that write echoes (if a device returns them)
cannot accidentally unblock an unrelated read on the same register.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Protocol

from linkerbot.comm.canfd import CANFDMessage
from linkerbot.exceptions import StateError, TimeoutError, ValidationError

from . import protocol


class O20DispatcherLike(Protocol):
    """Minimal CANFD dispatcher interface required by the O20 client.

    This protocol keeps O20 message construction independent of the concrete
    transport backend. The runtime uses CANFDMessageDispatcher; tests provide
    a lightweight fake.
    """

    def send(self, message: CANFDMessage) -> None:
        """Send one CANFD message."""
        ...

    def subscribe(self, callback: Callable[[CANFDMessage], None]) -> None:
        """Subscribe to incoming CANFD messages."""
        ...

    def unsubscribe(self, callback: Callable[[CANFDMessage], None]) -> None:
        """Unsubscribe from incoming CANFD messages."""
        ...

    def stop(self) -> None:
        """Stop dispatcher resources owned by the concrete backend."""
        ...


@dataclass(slots=True)
class _ResponseWaiter:
    event: threading.Event = field(default_factory=threading.Event)
    data: bytes | None = None
    error: Exception | None = None


class O20Client:
    """Low-level O20 register read/write router.

    O20Client builds protocol frames, sends them through a dispatcher-like
    transport, and routes incoming frames to pending read waiters keyed by
    ``(device_id, register)``. Writes are fire-and-forget by default because
    the O20 hand may or may not echo a write response depending on register.
    """

    def __init__(
        self,
        dispatcher: O20DispatcherLike,
        *,
        device_id: int,
        frame_type: int | None = None,
    ) -> None:
        """Initialize the protocol client.

        Args:
            dispatcher: Transport backend that sends and receives CANFD messages.
            device_id: O20 device ID used as the destination of every request.
            frame_type: Optional CANFD frame type override applied to every
                outgoing frame. When None, the dispatcher applies its default.

        Raises:
            ValidationError: If device_id is outside the documented O20 range.
        """
        protocol._validate_range(device_id, "device_id", 0, protocol.O20_DEVICE_ID_MAX)
        self._dispatcher = dispatcher
        self._device_id = device_id
        self._frame_type = frame_type
        self._lock = threading.Lock()
        self._transaction_lock = threading.Lock()
        # Guards multi-register tactile transactions. O20 splits each finger's
        # tactile payload across two independent registers (data1 + data2); if
        # two threads interleave their reads the (data1, data2) pair on each
        # thread can end up being cross-sampled from different acquisitions,
        # producing corrupt matrices. force_sensor uses tactile_transaction()
        # to hold this lock across the paired reads.
        self._tactile_lock = threading.Lock()
        self._pending: dict[tuple[int, int], _ResponseWaiter] = {}
        self._closed = False
        # Prefer the dispatcher's O(1) filtered subscription when present
        # (CANFDMessageDispatcher.subscribe_filter added in fix#141 to avoid
        # fan-out across every client on a shared bus). Fall back to the
        # broadcast subscribe contract for older dispatchers and test fakes.
        subscribe_filter = getattr(dispatcher, "subscribe_filter", None)
        if subscribe_filter is not None:
            subscribe_filter(self._frame_matches_client, self._on_message)
        else:
            self._dispatcher.subscribe(self._on_message)

    @property
    def device_id(self) -> int:
        """O20 device ID used by this client."""
        return self._device_id

    def write(
        self,
        *,
        register: int,
        payload: bytes,
        dlc: int | None = None,
    ) -> None:
        """Send an O20 register write without waiting for a response.

        Args:
            register: O20 register address to write.
            payload: Encoded register payload bytes.
            dlc: Optional CANFD DLC override.

        Raises:
            StateError: If the client is closed.
            ValidationError: If register or DLC is invalid.
        """
        self._ensure_open()
        self._dispatcher.send(
            self._message(register=register, write=True, payload=payload, dlc=dlc)
        )

    def read(self, *, register: int, timeout_ms: float) -> bytes:
        """Send an O20 register read and wait for the matching response payload.

        Args:
            register: O20 register address to read.
            timeout_ms: Time to wait for the response.

        Returns:
            Raw response payload bytes carrying the register value.

        Raises:
            ValidationError: If timeout_ms is not positive or the register is invalid.
            StateError: If the client is closed.
            TimeoutError: If no matching response arrives before the timeout.
        """
        with self._transaction_lock:
            self._validate_timeout(timeout_ms)
            self._ensure_open()
            protocol._validate_range(register, "register", 0, protocol.O20_REGISTER_MAX)
            request = self._message(
                register=register,
                write=False,
                payload=b"",
                dlc=protocol.O20_EMPTY_REQUEST_DLC,
            )
            key = (self._device_id, register)
            waiter = _ResponseWaiter()
            with self._lock:
                self._pending[key] = waiter
            try:
                self._dispatcher.send(request)
                if not waiter.event.wait(timeout_ms / 1000):
                    raise TimeoutError(
                        f"No O20 response received within {timeout_ms:.0f}ms"
                    )
                if waiter.error is not None:
                    raise waiter.error
                if waiter.data is None:
                    raise TimeoutError(
                        f"No O20 response received within {timeout_ms:.0f}ms"
                    )
                return waiter.data
            finally:
                with self._lock:
                    self._pending.pop(key, None)

    def close(self) -> None:
        """Unsubscribe from the dispatcher and wake any pending waiters."""
        if self._closed:
            return
        self._closed = True
        self._dispatcher.unsubscribe(self._on_message)
        error = StateError("O20 client is closed")
        with self._lock:
            pending = tuple(self._pending.values())
            self._pending.clear()
        for waiter in pending:
            waiter.error = error
            waiter.event.set()

    @contextmanager
    def tactile_transaction(self) -> Iterator[None]:
        """Serialize multi-register tactile reads so pairs stay atomic.

        O20 tactile payloads are split across two consecutive registers per
        finger. Without this lock, two threads reading tactile data
        concurrently may interleave their register reads, yielding
        cross-sampled (data1, data2) pairs. Wrap the paired reads in a
        ``with client.tactile_transaction():`` block to hold the tactile
        lock for the whole transaction:

        >>> with client.tactile_transaction():
        ...     data1 = client.read(register=REG_DATA1, timeout_ms=100)
        ...     data2 = client.read(register=REG_DATA2, timeout_ms=100)

        Normal (non-tactile) reads and all writes are unaffected — this lock
        is orthogonal to ``_transaction_lock`` and ``dispatcher._tx_lock``.
        """
        with self._tactile_lock:
            yield

    def _message(
        self, *, register: int, write: bool, payload: bytes, dlc: int | None
    ) -> CANFDMessage:
        return protocol.build_message(
            device_id=self._device_id,
            register=register,
            write=write,
            data=payload,
            dlc=dlc,
            frame_type=self._frame_type,
        )

    def _on_message(self, message: CANFDMessage) -> None:
        if not message.is_extended_id:
            return
        try:
            frame_id = protocol.parse_can_id(message.arbitration_id)
        except ValidationError:
            return
        if frame_id.device_id != self._device_id:
            return
        # Only read responses (WriteFlag=0) can satisfy a pending read waiter.
        # Write echoes share the same (device_id, register) tuple but must not
        # unblock readers, so they are dropped here.
        if frame_id.write != protocol.O20_ACCESS_READ:
            return
        with self._lock:
            waiter = self._pending.get((frame_id.device_id, frame_id.register))
        if waiter is None:
            return
        waiter.data = message.data
        waiter.event.set()

    def _frame_matches_client(self, message: CANFDMessage) -> bool:
        """Predicate for ``dispatcher.subscribe_filter``.

        Cheap pre-filter so the dispatcher only routes frames whose
        ``device_id`` matches this client. On a shared bus with N O20 hands,
        this turns the per-frame fan-out from O(N) into O(1).
        """
        if not message.is_extended_id:
            return False
        try:
            frame_id = protocol.parse_can_id(message.arbitration_id)
        except ValidationError:
            return False
        return frame_id.device_id == self._device_id

    def _ensure_open(self) -> None:
        if self._closed:
            raise StateError("O20 client is closed")

    def _validate_timeout(self, timeout_ms: float) -> None:
        if timeout_ms <= 0:
            raise ValidationError("timeout_ms must be positive")
