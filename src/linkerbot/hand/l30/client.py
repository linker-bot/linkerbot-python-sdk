"""Transport-neutral L30 protocol client."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from linkerbot.comm.canfd import CANFDMessage
from linkerbot.exceptions import StateError, TimeoutError, ValidationError

from . import protocol


class L30DispatcherLike(Protocol):
    """Minimal CANFD dispatcher interface required by the L30 protocol client.

    This protocol keeps L30 message construction and response routing independent
    from the concrete transport backend. The runtime uses CANFDMessageDispatcher;
    tests and future socketcan-fd support can provide another implementation.
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


@dataclass(slots=True)
class _TactileWaiter:
    event: threading.Event = field(default_factory=threading.Event)
    first_frame: bytes | None = None
    second_frame: bytes | None = None
    error: Exception | None = None


class L30Client:
    """Low-level L30 request, response, tactile, and report router.

    L30Client builds protocol frames, sends them through a dispatcher-like
    transport, and routes incoming frames into three categories: matching
    request/ACK waiters, two-frame tactile waiters, and periodic report handlers.
    """

    def __init__(
        self, dispatcher: L30DispatcherLike, *, node_id: int, host_id: int
    ) -> None:
        """Initialize the protocol client.

        Args:
            dispatcher: Transport backend that sends and receives CANFD messages.
            node_id: L30 device node ID used as destination ID for requests.
            host_id: Host node ID used as source ID for requests.

        Raises:
            ValidationError: If node_id or host_id is outside the L30 ID range.
        """
        protocol._validate_range(
            node_id, "node_id", protocol.L30_NODE_ID_MIN, protocol.L30_NODE_ID_MAX
        )
        protocol._validate_range(
            host_id, "host_id", protocol.L30_HOST_ID_MIN, protocol.L30_HOST_ID_MAX
        )
        self._dispatcher = dispatcher
        self._node_id = node_id
        self._host_id = host_id
        self._lock = threading.Lock()
        self._transaction_lock = threading.Lock()
        self._pending: dict[int, _ResponseWaiter] = {}
        self._tactile_pending: dict[int, _TactileWaiter] = {}
        self._report_handlers: dict[int, list[Callable[[bytes], None]]] = {}
        self._closed = False
        self._dispatcher.subscribe(self._on_message)

    @property
    def node_id(self) -> int:
        """L30 device node ID used by this client."""
        return self._node_id

    @property
    def host_id(self) -> int:
        """Host node ID used by this client."""
        return self._host_id

    def send_no_ack(
        self, *, parent: int, subcmd: int, payload: bytes, dlc: int | None = None
    ) -> None:
        """Send an L30 write command without waiting for an ACK.

        Args:
            parent: L30 parent command field.
            subcmd: L30 subcommand field.
            payload: Encoded L30 payload bytes.
            dlc: Optional CANFD DLC override.

        Raises:
            ValidationError: If the client is closed or frame fields are invalid.
        """
        self._ensure_open()
        self._dispatcher.send(
            self._message(
                parent=parent,
                subcmd=subcmd,
                access=protocol.L30_ACCESS_WRITE,
                payload=payload,
                dlc=dlc,
            )
        )

    def request_ack(
        self,
        *,
        parent: int,
        subcmd: int,
        payload: bytes,
        timeout_ms: float,
        dlc: int | None = None,
    ) -> bytes:
        """Send an L30 write command and wait for its ACK payload.

        Args:
            parent: L30 parent command field.
            subcmd: L30 subcommand field.
            payload: Encoded L30 payload bytes.
            timeout_ms: Time to wait for the matching ACK.
            dlc: Optional CANFD DLC override.

        Returns:
            Raw ACK payload bytes.

        Raises:
            ValidationError: If timeout_ms is invalid or the client is closed.
            TimeoutError: If no matching ACK arrives before the timeout.
        """
        return self._request(
            parent=parent,
            subcmd=subcmd,
            access=protocol.L30_ACCESS_WRITE,
            payload=payload,
            timeout_ms=timeout_ms,
            dlc=dlc,
        )

    def read(self, *, parent: int, subcmd: int, timeout_ms: float) -> bytes:
        """Send an L30 read request and wait for the response payload.

        Args:
            parent: L30 parent command field.
            subcmd: L30 subcommand field.
            timeout_ms: Time to wait for the matching response.

        Returns:
            Raw response payload bytes.

        Raises:
            ValidationError: If timeout_ms is invalid or the client is closed.
            TimeoutError: If no matching response arrives before the timeout.
        """
        return self._request(
            parent=parent,
            subcmd=subcmd,
            access=protocol.L30_ACCESS_READ,
            payload=protocol.empty_request_payload(),
            timeout_ms=timeout_ms,
            dlc=protocol.L30_EMPTY_REQUEST_DLC,
        )

    def read_tactile(self, *, subcmd: int, timeout_ms: float) -> bytes:
        """Read one tactile sensor payload assembled from two L30 frames.

        Args:
            subcmd: Finger subcommand defined by the tactile parent command.
            timeout_ms: Time to wait for both tactile response frames.

        Returns:
            The 72-byte tactile payload without protocol headers or CANFD padding.

        Raises:
            ValidationError: If timeout_ms is invalid or the client is closed.
            TimeoutError: If both tactile frames do not arrive before the timeout.
            ProtocolError: If transaction ordering or payload validation fails.
        """
        with self._transaction_lock:
            self._validate_timeout(timeout_ms)
            self._ensure_open()
            request = self._message(
                parent=protocol.L30_PARENT_TACTILE,
                subcmd=subcmd,
                access=protocol.L30_ACCESS_READ,
                payload=protocol.empty_request_payload(),
                dlc=protocol.L30_EMPTY_REQUEST_DLC,
            )
            response_id = protocol.expected_response_id(request.arbitration_id)
            waiter = _TactileWaiter()
            with self._lock:
                self._tactile_pending[response_id] = waiter
            try:
                self._dispatcher.send(request)
                if not waiter.event.wait(timeout_ms / 1000):
                    raise TimeoutError(
                        f"No L30 tactile response received within {timeout_ms:.0f}ms"
                    )
                if waiter.error is not None:
                    raise waiter.error
                if waiter.first_frame is None or waiter.second_frame is None:
                    raise protocol.ProtocolError("incomplete tactile response")
                return protocol.assemble_tactile_payload(
                    waiter.first_frame, waiter.second_frame
                )
            finally:
                with self._lock:
                    self._tactile_pending.pop(response_id, None)

    def add_report_handler(
        self, subcmd: int, callback: Callable[[bytes], None]
    ) -> None:
        """Register a callback for one periodic report subcommand.

        Args:
            subcmd: Periodic report subcommand to route.
            callback: Function called with raw report payload bytes.
        """
        with self._lock:
            self._report_handlers.setdefault(subcmd, []).append(callback)

    def remove_report_handler(
        self, subcmd: int, callback: Callable[[bytes], None]
    ) -> None:
        """Unregister a periodic report callback.

        Args:
            subcmd: Periodic report subcommand to update.
            callback: Previously registered callback.
        """
        with self._lock:
            handlers = self._report_handlers.get(subcmd)
            if handlers is None:
                return
            if callback in handlers:
                handlers.remove(callback)
            if not handlers:
                self._report_handlers.pop(subcmd, None)

    def close(self) -> None:
        """Unsubscribe from the dispatcher and wake pending waiters."""
        if self._closed:
            return
        self._closed = True
        self._dispatcher.unsubscribe(self._on_message)
        error = StateError("L30 client is closed")
        with self._lock:
            pending = tuple(self._pending.values())
            tactile_pending = tuple(self._tactile_pending.values())
            self._pending.clear()
            self._tactile_pending.clear()
            self._report_handlers.clear()
        for waiter in pending:
            waiter.error = error
            waiter.event.set()
        for waiter in tactile_pending:
            waiter.error = error
            waiter.event.set()

    def _request(
        self,
        *,
        parent: int,
        subcmd: int,
        access: int,
        payload: bytes,
        timeout_ms: float,
        dlc: int | None,
    ) -> bytes:
        with self._transaction_lock:
            self._validate_timeout(timeout_ms)
            self._ensure_open()
            request = self._message(
                parent=parent, subcmd=subcmd, access=access, payload=payload, dlc=dlc
            )
            response_id = protocol.expected_response_id(request.arbitration_id)
            waiter = _ResponseWaiter()
            with self._lock:
                self._pending[response_id] = waiter
            try:
                self._dispatcher.send(request)
                if not waiter.event.wait(timeout_ms / 1000):
                    raise TimeoutError(
                        f"No L30 response received within {timeout_ms:.0f}ms"
                    )
                if waiter.error is not None:
                    raise waiter.error
                if waiter.data is None:
                    raise TimeoutError(
                        f"No L30 response received within {timeout_ms:.0f}ms"
                    )
                return waiter.data
            finally:
                with self._lock:
                    self._pending.pop(response_id, None)

    def _message(
        self, *, parent: int, subcmd: int, access: int, payload: bytes, dlc: int | None
    ) -> CANFDMessage:
        return protocol.build_message(
            parent=parent,
            subcmd=subcmd,
            access=access,
            dst_id=self._node_id,
            src_id=self._host_id,
            data=payload,
            dlc=dlc,
        )

    def _on_message(self, message: CANFDMessage) -> None:
        if not message.is_extended_id:
            return
        try:
            frame_id = protocol.parse_can_id(message.arbitration_id)
        except ValidationError:
            return
        if frame_id.dst_id != self._host_id or frame_id.src_id != self._node_id:
            return
        if self._handle_pending(message):
            return
        if self._handle_tactile(message):
            return
        self._handle_report(frame_id, message.data)

    def _handle_pending(self, message: CANFDMessage) -> bool:
        # Normal read responses and write ACKs are matched by exact response ID.
        with self._lock:
            waiter = self._pending.get(message.arbitration_id)
        if waiter is None:
            return False
        waiter.data = message.data
        waiter.event.set()
        return True

    def _handle_tactile(self, message: CANFDMessage) -> bool:
        # Tactile reads use one response ID with two transaction-control frames.
        with self._lock:
            waiter = self._tactile_pending.get(message.arbitration_id)
        if waiter is None:
            return False
        try:
            if len(message.data) <= 1:
                raise protocol.ProtocolError("tactile response too short")
            if message.data[1] == protocol.L30_TACTILE_FIRST_FRAME_TRANSACTION:
                waiter.first_frame = message.data
            elif message.data[1] == protocol.L30_TACTILE_SECOND_FRAME_TRANSACTION:
                waiter.second_frame = message.data
            else:
                raise protocol.ProtocolError(
                    f"unexpected tactile transaction 0x{message.data[1]:02X}"
                )
            if waiter.first_frame is not None and waiter.second_frame is not None:
                waiter.event.set()
        except Exception as error:
            waiter.error = error
            waiter.event.set()
        return True

    def _handle_report(self, frame_id: protocol.L30FrameId, data: bytes) -> None:
        # Periodic reports are unsolicited read frames from the periodic parent.
        if (
            frame_id.access != protocol.L30_ACCESS_READ
            or frame_id.parent != protocol.L30_PARENT_PERIODIC
        ):
            return
        with self._lock:
            handlers = tuple(self._report_handlers.get(frame_id.subcmd, ()))
        for handler in handlers:
            handler(data)

    def _ensure_open(self) -> None:
        if self._closed:
            raise StateError("L30 client is closed")

    def _validate_timeout(self, timeout_ms: float) -> None:
        if timeout_ms <= 0:
            raise ValidationError("timeout_ms must be positive")
