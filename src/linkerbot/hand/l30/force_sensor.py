"""Tactile force sensor access for L30."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

import numpy as np
from numpy.typing import NDArray

from linkerbot.relay import DataRelay

from .client import L30Client

L30_TACTILE_ROWS = 12
L30_TACTILE_COLUMNS = 6


class Finger(str, Enum):
    """L30 tactile force sensor finger names."""

    THUMB = "thumb"
    INDEX = "index"
    MIDDLE = "middle"
    RING = "ring"
    PINKY = "pinky"


_FINGER_SUBCOMMANDS = {
    Finger.THUMB: 0x01,
    Finger.INDEX: 0x02,
    Finger.MIDDLE: 0x03,
    Finger.RING: 0x04,
    Finger.PINKY: 0x05,
}


@dataclass(frozen=True, slots=True)
class FingerForceData:
    """Immutable tactile data for one L30 finger.

    Attributes:
        finger: Finger that was read.
        values: 12x6 uint8 tactile matrix for the finger.
        timestamp: Unix timestamp when the tactile payload was decoded.
    """

    finger: Finger
    values: NDArray[np.uint8]
    timestamp: float


@dataclass(frozen=True, slots=True)
class AllFingersData:
    """Immutable tactile data for all five L30 fingers.

    Attributes:
        thumb: 12x6 uint8 tactile matrix for the thumb.
        index: 12x6 uint8 tactile matrix for the index finger.
        middle: 12x6 uint8 tactile matrix for the middle finger.
        ring: 12x6 uint8 tactile matrix for the ring finger.
        pinky: 12x6 uint8 tactile matrix for the pinky finger.
        timestamp: Unix timestamp when the all-finger read completed.
    """

    thumb: NDArray[np.uint8]
    index: NDArray[np.uint8]
    middle: NDArray[np.uint8]
    ring: NDArray[np.uint8]
    pinky: NDArray[np.uint8]
    timestamp: float


class ForceSensorManager:
    """Manager for L30 tactile force sensor reads.

    Each finger is returned as a 12x6 uint8 matrix assembled from the L30 tactile
    two-frame CANFD response. The all-finger snapshot is updated only by
    get_blocking(), not by single-finger reads.
    """

    def __init__(self, client: L30Client) -> None:
        """Initialize the force sensor manager.

        Args:
            client: L30 protocol client used for tactile query transactions.
        """
        self._client = client
        self._relay = DataRelay[AllFingersData]()

    def get_finger(self, finger: Finger, timeout_ms: float = 1000) -> FingerForceData:
        """Read tactile data for one finger.

        Args:
            finger: Finger to read.
            timeout_ms: Time to wait for the complete two-frame tactile response.

        Returns:
            FingerForceData with a 12x6 uint8 matrix.

        Raises:
            TimeoutError: If the tactile response is incomplete before timeout.
            ProtocolError: If the tactile status, transaction order, or payload
                shape is invalid.
        """
        payload = self._client.read_tactile(
            subcmd=_FINGER_SUBCOMMANDS[finger], timeout_ms=timeout_ms
        )
        values = (
            np.frombuffer(payload, dtype=np.uint8)
            .copy()
            .reshape(L30_TACTILE_ROWS, L30_TACTILE_COLUMNS)
        )
        values.setflags(write=False)
        return FingerForceData(finger=finger, values=values, timestamp=time.time())

    def get_blocking(self, timeout_ms: float = 1000) -> AllFingersData:
        """Read tactile data for all five fingers and update the snapshot.

        Args:
            timeout_ms: Time to wait for each finger response.

        Returns:
            AllFingersData containing one 12x6 matrix per finger.

        Raises:
            TimeoutError: If any finger response is incomplete before timeout.
            ProtocolError: If any tactile response is invalid.
        """
        fingers = {
            finger: self.get_finger(finger, timeout_ms=timeout_ms) for finger in Finger
        }
        data = AllFingersData(
            thumb=fingers[Finger.THUMB].values,
            index=fingers[Finger.INDEX].values,
            middle=fingers[Finger.MIDDLE].values,
            ring=fingers[Finger.RING].values,
            pinky=fingers[Finger.PINKY].values,
            timestamp=time.time(),
        )
        self._relay.push(data)
        return data

    def get_snapshot(self) -> AllFingersData | None:
        """Return the latest cached all-finger tactile data.

        Returns:
            Cached AllFingersData, or None if get_blocking() has not completed.
        """
        return self._relay.snapshot()

    def _send_sense_request(self) -> None:
        self.get_blocking(timeout_ms=1000)

    def _set_event_sink(self, sink: Callable[[AllFingersData], None]) -> None:
        self._relay.set_sink(sink)
