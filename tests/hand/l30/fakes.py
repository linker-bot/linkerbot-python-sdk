from __future__ import annotations

from collections.abc import Callable

from linkerbot.comm.canfd import CANFDMessage


class FakeDispatcher:
    def __init__(self) -> None:
        self.sent: list[CANFDMessage] = []
        self.subscribers: list[Callable[[CANFDMessage], None]] = []
        self.filtered_subscribers: list[
            tuple[Callable[[CANFDMessage], bool], Callable[[CANFDMessage], None]]
        ] = []
        self.stopped = False

    def send(self, message: CANFDMessage) -> None:
        self.sent.append(message)

    def subscribe(self, callback: Callable[[CANFDMessage], None]) -> None:
        self.subscribers.append(callback)

    def subscribe_filter(
        self,
        predicate: Callable[[CANFDMessage], bool],
        callback: Callable[[CANFDMessage], None],
    ) -> None:
        """Mirror the dispatcher's filtered-subscription API.

        Recorded separately so tests that want to verify a client took the
        filter path can inspect ``filtered_subscribers``; ``inject`` still
        invokes both kinds of subscriber so existing test setups keep
        working without changes.
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
