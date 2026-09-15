from __future__ import annotations

from collections.abc import Callable, Iterable

from linkerbot.comm.canfd import CANFDMessage


class FakeDispatcher:
    """Synchronous dispatcher for HandProtocol unit tests."""

    def __init__(
        self,
        responder: Callable[[CANFDMessage], Iterable[CANFDMessage]] | None = None,
    ) -> None:
        self.sent: list[CANFDMessage] = []
        self.subscribers: list[Callable[[CANFDMessage], None]] = []
        self.filtered_subscribers: list[
            tuple[Callable[[CANFDMessage], bool], Callable[[CANFDMessage], None]]
        ] = []
        self.stopped = False
        self._responder = responder

    def send(self, message: CANFDMessage) -> None:
        self.sent.append(message)
        if self._responder is not None:
            for response in self._responder(message):
                self.inject(response)

    def subscribe(self, callback: Callable[[CANFDMessage], None]) -> None:
        self.subscribers.append(callback)

    def subscribe_filter(
        self,
        predicate: Callable[[CANFDMessage], bool],
        callback: Callable[[CANFDMessage], None],
    ) -> None:
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
