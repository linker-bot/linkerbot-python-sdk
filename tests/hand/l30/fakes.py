from __future__ import annotations

from collections.abc import Callable

from linkerbot.comm.canfd import CANFDMessage


class FakeDispatcher:
    def __init__(self) -> None:
        self.sent: list[CANFDMessage] = []
        self.subscribers: list[Callable[[CANFDMessage], None]] = []
        self.stopped = False

    def send(self, message: CANFDMessage) -> None:
        self.sent.append(message)

    def subscribe(self, callback: Callable[[CANFDMessage], None]) -> None:
        self.subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[CANFDMessage], None]) -> None:
        if callback in self.subscribers:
            self.subscribers.remove(callback)

    def stop(self) -> None:
        self.stopped = True

    def inject(self, message: CANFDMessage) -> None:
        for callback in tuple(self.subscribers):
            callback(message)
