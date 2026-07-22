"""Structural transport contracts shared by classic CAN hand managers."""

from collections.abc import Callable
from typing import Protocol

import can


class CANDispatcherLike(Protocol):
    """Minimal classic CAN dispatcher contract used by sensor managers."""

    def send(self, msg: can.Message) -> None:
        """Queue one CAN message for transmission."""
        ...

    def subscribe(self, callback: Callable[[can.Message], None]) -> None:
        """Subscribe to received CAN messages."""
        ...
