from __future__ import annotations

from collections.abc import Callable

from linkerbot.comm.canfd import CANFDMessage
from linkerbot.hand.o20 import protocol


class FakeDispatcher:
    """Lightweight CANFD dispatcher used by the O20 unit tests.

    The dispatcher records sent frames, lets tests inject incoming frames, and
    optionally auto-responds to register reads from a register-to-payload
    mapping. Auto-responses run synchronously inside ``send()`` so that a
    blocking ``read()`` call returns inside the same thread.
    """

    def __init__(
        self,
        responses: dict[int, bytes] | None = None,
    ) -> None:
        self.sent: list[CANFDMessage] = []
        self.subscribers: list[Callable[[CANFDMessage], None]] = []
        self.filtered_subscribers: list[
            tuple[Callable[[CANFDMessage], bool], Callable[[CANFDMessage], None]]
        ] = []
        self.stopped = False
        self._responses: dict[int, bytes] = dict(responses or {})

    def send(self, message: CANFDMessage) -> None:
        self.sent.append(message)
        if message.is_extended_id:
            try:
                frame_id = protocol.parse_can_id(message.arbitration_id)
            except Exception:
                return
            if frame_id.write == protocol.O20_ACCESS_READ:
                payload = self._responses.get(frame_id.register)
                if payload is not None:
                    self.inject(
                        CANFDMessage(
                            arbitration_id=protocol.build_can_id(
                                device_id=frame_id.device_id,
                                register=frame_id.register,
                                write=False,
                            ),
                            data=payload,
                        )
                    )

    def subscribe(self, callback: Callable[[CANFDMessage], None]) -> None:
        self.subscribers.append(callback)

    def subscribe_filter(
        self,
        predicate: Callable[[CANFDMessage], bool],
        callback: Callable[[CANFDMessage], None],
    ) -> None:
        """Mirror the CANFDMessageDispatcher filtered-subscription API.

        Recorded separately so tests that want to verify the client took the
        filter path can inspect ``filtered_subscribers``. ``inject`` invokes
        both plain and filtered subscribers.
        """
        self.filtered_subscribers.append((predicate, callback))

    def unsubscribe(self, callback: Callable[[CANFDMessage], None]) -> None:
        if callback in self.subscribers:
            self.subscribers.remove(callback)
        self.filtered_subscribers = [
            (predicate, existing)
            for predicate, existing in self.filtered_subscribers
            if existing is not callback
        ]

    def stop(self) -> None:
        self.stopped = True

    def inject(self, message: CANFDMessage) -> None:
        for callback in tuple(self.subscribers):
            callback(message)
        for predicate, callback in tuple(self.filtered_subscribers):
            if predicate(message):
                callback(message)

    def set_response(self, register: int, payload: bytes) -> None:
        """Register a payload that will be returned for reads of ``register``."""
        self._responses[register] = payload
