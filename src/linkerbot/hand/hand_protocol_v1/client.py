"""Serialized request/response client for HandProtocol_v1.0 objects."""

from __future__ import annotations

import math
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Protocol

from linkerbot.comm.canfd import CANFDMessage
from linkerbot.exceptions import StateError, TimeoutError, ValidationError

from . import protocol


class HandProtocolV1DispatcherLike(Protocol):
    """Minimal dispatcher contract required by :class:`HandProtocolV1`."""

    def send(self, message: CANFDMessage) -> None:
        """Queue one CAN-FD message for transmission."""
        ...

    def subscribe(self, callback: Callable[[CANFDMessage], None]) -> None:
        """Subscribe to received CAN-FD messages."""
        ...

    def unsubscribe(self, callback: Callable[[CANFDMessage], None]) -> None:
        """Remove a previously registered receive callback."""
        ...

    def stop(self) -> None:
        """Stop resources owned by the concrete dispatcher."""
        ...


@dataclass(slots=True)
class _PendingResponse:
    main_index: int
    sub_index: int
    length: int
    rts: bool
    buffer: bytearray = field(init=False)
    received: bytearray = field(init=False)
    event: threading.Event = field(default_factory=threading.Event)
    error: Exception | None = None

    def __post_init__(self) -> None:
        self.buffer = bytearray(self.length)
        self.received = bytearray(self.length)


class HandProtocolV1:
    """Transport-neutral HOP object client.

    HOP carries no transaction identifier and uses one response CAN ID for all
    objects. Consequently every request is serialized. Long objects are
    assembled from response fragments by matching their main index and SI byte
    ranges until every requested byte has arrived.
    """

    def __init__(
        self,
        dispatcher: HandProtocolV1DispatcherLike,
        *,
        request_id: int = protocol.HAND_PROTOCOL_DEFAULT_REQUEST_ID,
        response_id: int | None = None,
        frame_type: int | None = protocol.HAND_PROTOCOL_DEFAULT_FRAME_TYPE,
    ) -> None:
        """Bind one HOP endpoint to a CAN-FD dispatcher."""
        if response_id is None:
            response_id = protocol.response_id_for_request(request_id)
        else:
            protocol._validate_standard_id(request_id, "request_id")
            protocol._validate_standard_id(response_id, "response_id")
        if request_id == response_id:
            raise ValidationError("request_id and response_id must be different")
        protocol._validate_frame_type(frame_type)

        self._dispatcher = dispatcher
        self._request_id = request_id
        self._response_id = response_id
        self._frame_type = frame_type
        self._state_lock = threading.Lock()
        self._send_condition = threading.Condition(self._state_lock)
        self._sending_threads: dict[int, int] = {}
        self._transaction_lock = threading.RLock()
        self._pending: _PendingResponse | None = None
        self._closed = False

        # Bound-method objects are recreated on attribute access. Keep the exact
        # subscribed instances so identity-based dispatcher removal is reliable.
        self._message_callback = self._on_message
        self._filter_callback = self._frame_matches_endpoint
        subscribe_filter = getattr(dispatcher, "subscribe_filter", None)
        if subscribe_filter is not None:
            subscribe_filter(self._filter_callback, self._message_callback)
        else:
            dispatcher.subscribe(self._message_callback)

    @property
    def request_id(self) -> int:
        """Standard CAN ID used for HOP requests."""
        return self._request_id

    @property
    def response_id(self) -> int:
        """Standard CAN ID expected on HOP responses."""
        return self._response_id

    def read(
        self,
        *,
        main_index: int,
        sub_index: int = 0,
        length: int,
        rts: bool = False,
        timeout_ms: float = 100,
    ) -> bytes:
        """Read one state or set-point byte range from a HOP object."""
        message = protocol.build_read_message(
            request_id=self._request_id,
            main_index=main_index,
            sub_index=sub_index,
            length=length,
            rts=rts,
            frame_type=self._frame_type,
        )
        return self._exchange(
            message,
            main_index=main_index,
            sub_index=sub_index,
            length=length,
            rts=rts,
            timeout_ms=timeout_ms,
        )

    def write(
        self,
        *,
        main_index: int,
        sub_index: int = 0,
        payload: bytes,
        timeout_ms: float = 100,
    ) -> bytes:
        """Write one single-frame object slice and wait for its response."""
        message = protocol.build_write_message(
            request_id=self._request_id,
            main_index=main_index,
            sub_index=sub_index,
            payload=payload,
            frame_type=self._frame_type,
        )
        return self._exchange(
            message,
            main_index=main_index,
            sub_index=sub_index,
            length=len(payload),
            rts=False,
            timeout_ms=timeout_ms,
        )

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Keep several object operations contiguous on the shared endpoint."""
        with self._transaction_lock:
            self._ensure_open()
            yield

    def close(self) -> None:
        """Unsubscribe and wake a pending request. Idempotent."""
        current_thread = threading.get_ident()
        with self._send_condition:
            if self._closed:
                return
            self._closed = True
            pending = self._pending
            self._pending = None
            if pending is not None:
                pending.error = StateError("HandProtocolV1 client is closed")
                pending.event.set()
            self._send_condition.wait_for(
                lambda: (
                    not any(
                        thread_id != current_thread
                        for thread_id in self._sending_threads
                    )
                )
            )
        self._dispatcher.unsubscribe(self._message_callback)

    def _exchange(
        self,
        message: CANFDMessage,
        *,
        main_index: int,
        sub_index: int,
        length: int,
        rts: bool,
        timeout_ms: float,
    ) -> bytes:
        timeout_seconds = _validate_timeout(timeout_ms)
        with self._transaction_lock:
            self._ensure_open()
            pending = _PendingResponse(main_index, sub_index, length, rts)
            with self._state_lock:
                self._ensure_open()
                self._pending = pending
            try:
                self._send_message(message)
                if not pending.event.wait(timeout_seconds):
                    raise TimeoutError(
                        "No complete HandProtocol response for "
                        f"MI=0x{main_index:02X}, SI=0x{sub_index:02X}, "
                        f"length={length} within {timeout_ms:.0f}ms"
                    )
                if pending.error is not None:
                    raise pending.error
                return bytes(pending.buffer)
            finally:
                with self._state_lock:
                    if self._pending is pending:
                        self._pending = None

    def _send_message(self, message: CANFDMessage) -> None:
        """Send only while open and let ``close`` drain reserved sends."""
        current_thread = threading.get_ident()
        with self._send_condition:
            self._ensure_open()
            self._sending_threads[current_thread] = (
                self._sending_threads.get(current_thread, 0) + 1
            )
        try:
            self._dispatcher.send(message)
        finally:
            with self._send_condition:
                remaining = self._sending_threads[current_thread] - 1
                if remaining:
                    self._sending_threads[current_thread] = remaining
                else:
                    del self._sending_threads[current_thread]
                self._send_condition.notify_all()

    def _on_message(self, message: CANFDMessage) -> None:
        # Filter again for legacy dispatchers that only support broadcast
        # subscriptions. Filter-aware dispatchers already perform this check.
        if not self._frame_matches_endpoint(message):
            return
        try:
            frame = protocol.decode_frame(message.data)
        except protocol.HandProtocolError as error:
            self._fail_pending(error)
            return

        with self._state_lock:
            pending = self._pending
            if pending is None:
                return

            if (
                frame.main_index == protocol.HAND_PROTOCOL_ERROR_MAIN_INDEX
                and pending.main_index != protocol.HAND_PROTOCOL_ERROR_MAIN_INDEX
            ):
                if frame.effective_length != 1:
                    pending.error = protocol.HandProtocolError(
                        "malformed HandProtocol error response: EDL must be 1"
                    )
                else:
                    pending.error = protocol.HandProtocolDeviceError(
                        error_index=frame.sub_index,
                        error_code=frame.payload[0],
                    )
                pending.event.set()
                return

            if frame.main_index != pending.main_index:
                return
            if frame.rts != pending.rts:
                return
            if frame.effective_length == 0:
                pending.error = protocol.HandProtocolError(
                    "empty HandProtocol response fragment"
                )
                pending.event.set()
                return

            fragment_start = frame.sub_index
            fragment_end = fragment_start + frame.effective_length
            expected_start = pending.sub_index
            expected_end = expected_start + pending.length
            # A delayed fragment from an earlier serialized request can share
            # the same MI. Ignore ranges that do not belong to this request.
            if fragment_start < expected_start or fragment_end > expected_end:
                return

            relative_start = fragment_start - expected_start
            for offset, value in enumerate(frame.payload, start=relative_start):
                if pending.received[offset] and pending.buffer[offset] != value:
                    pending.error = protocol.HandProtocolError(
                        "conflicting duplicate HandProtocol response fragment"
                    )
                    pending.event.set()
                    return
                pending.buffer[offset] = value
                pending.received[offset] = 1
            if all(pending.received):
                pending.event.set()

    def _fail_pending(self, error: Exception) -> None:
        with self._state_lock:
            pending = self._pending
            if pending is None:
                return
            pending.error = error
            pending.event.set()

    def _frame_matches_endpoint(self, message: CANFDMessage) -> bool:
        return (
            not message.is_extended_id and message.arbitration_id == self._response_id
        )

    def _ensure_open(self) -> None:
        if self._closed:
            raise StateError("HandProtocolV1 client is closed")


def _validate_timeout(timeout_ms: float) -> float:
    if not isinstance(timeout_ms, (int, float)) or isinstance(timeout_ms, bool):
        raise ValidationError("timeout_ms must be int or float")
    if not math.isfinite(timeout_ms) or timeout_ms <= 0:
        raise ValidationError("timeout_ms must be finite and positive")
    return float(timeout_ms) / 1000
