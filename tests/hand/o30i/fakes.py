from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from linkerbot.comm.canfd import CANFDMessage


@dataclass(frozen=True, slots=True)
class RecordedWrite:
    main_index: int
    sub_index: int
    payload: bytes


class FakeO30iDispatcher:
    """Synchronous HOP endpoint used by O30i device-level tests."""

    def __init__(
        self,
        objects: Mapping[int | tuple[int, bool], bytes] | None = None,
        *,
        response_id: int = 0x401,
    ) -> None:
        self.sent: list[CANFDMessage] = []
        self.writes: list[RecordedWrite] = []
        self.subscribers: list[Callable[[CANFDMessage], None]] = []
        self.filtered_subscribers: list[
            tuple[Callable[[CANFDMessage], bool], Callable[[CANFDMessage], None]]
        ] = []
        self.stopped = False
        self.response_id = response_id
        self.objects = dict(objects or {})

    def send(self, message: CANFDMessage) -> None:
        self.sent.append(message)
        if message.is_extended_id or len(message.data) < 3:
            return
        control, sub_index, effective_length = message.data[:3]
        main_index = control & 0x7F
        rts = bool(control & 0x80)
        if len(message.data) == 3:
            source = self.objects.get((main_index, rts))
            if source is None:
                source = self.objects.get(main_index)
            if source is None:
                return
            requested_end = sub_index + effective_length
            if requested_end > len(source):
                self._inject_payload(0x4F, sub_index, b"\x02")
                return
            response = bytes(source[sub_index:requested_end])
            response_control = main_index | (0x80 if rts else 0)
            for relative_offset in range(0, len(response), 61):
                fragment = response[relative_offset : relative_offset + 61]
                self._inject_payload(
                    response_control,
                    sub_index + relative_offset,
                    fragment,
                )
            return

        payload = bytes(message.data[3:])
        if len(payload) != effective_length:
            return
        self.writes.append(RecordedWrite(main_index, sub_index, payload))
        self._inject_payload(main_index, sub_index, payload)

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

    def _inject_payload(
        self,
        main_index: int,
        sub_index: int,
        payload: bytes,
    ) -> None:
        self.inject(
            CANFDMessage(
                arbitration_id=self.response_id,
                data=bytes((main_index, sub_index, len(payload))) + payload,
                is_extended_id=False,
                frame_type=0x04,
            )
        )
