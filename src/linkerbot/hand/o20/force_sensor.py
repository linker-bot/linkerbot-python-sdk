"""Tactile force sensor access for O20.

Each finger's tactile data is split across two registers on the wire: a 64-byte
front segment and a 9-byte back segment. The SDK reads both segments, then
assembles a 73-byte block whose first byte is the online flag and whose
remaining 72 bytes form a 12x6 unsigned-byte matrix.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

import numpy as np
from numpy.typing import NDArray

from linkerbot.exceptions import ValidationError
from linkerbot.relay import DataRelay

from . import protocol
from .client import O20Client


class Finger(str, Enum):
    """O20 tactile force sensor finger names."""

    THUMB = "thumb"
    INDEX = "index"
    MIDDLE = "middle"
    RING = "ring"
    PINKY = "pinky"


_FINGER_REGISTERS: dict[Finger, tuple[int, int]] = {
    Finger.THUMB: (
        protocol.O20_REG_TACTILE_THUMB_DATA1,
        protocol.O20_REG_TACTILE_THUMB_DATA2,
    ),
    Finger.INDEX: (
        protocol.O20_REG_TACTILE_INDEX_DATA1,
        protocol.O20_REG_TACTILE_INDEX_DATA2,
    ),
    Finger.MIDDLE: (
        protocol.O20_REG_TACTILE_MIDDLE_DATA1,
        protocol.O20_REG_TACTILE_MIDDLE_DATA2,
    ),
    Finger.RING: (
        protocol.O20_REG_TACTILE_RING_DATA1,
        protocol.O20_REG_TACTILE_RING_DATA2,
    ),
    Finger.PINKY: (
        protocol.O20_REG_TACTILE_PINKY_DATA1,
        protocol.O20_REG_TACTILE_PINKY_DATA2,
    ),
}


@dataclass(frozen=True, slots=True)
class O20FingerForceData:
    """Immutable tactile data for one O20 finger.

    Attributes:
        finger: Finger that was read.
        online: True when the on-finger sensor reports itself as online.
        values: 12x6 uint8 tactile matrix for the finger.
        timestamp: Unix timestamp when the tactile payload was decoded.
    """

    finger: Finger
    online: bool
    values: NDArray[np.uint8]
    timestamp: float


@dataclass(frozen=True, slots=True)
class O20AllFingersData:
    """Immutable tactile data for all five O20 fingers.

    Attributes:
        thumb: Tactile readback for the thumb.
        index: Tactile readback for the index finger.
        middle: Tactile readback for the middle finger.
        ring: Tactile readback for the ring finger.
        pinky: Tactile readback for the pinky finger.
        timestamp: Unix timestamp when the all-finger read completed.
    """

    thumb: O20FingerForceData
    index: O20FingerForceData
    middle: O20FingerForceData
    ring: O20FingerForceData
    pinky: O20FingerForceData
    timestamp: float


class FingerForceSensor:
    """Single-finger tactile reader bound to one O20 finger."""

    def __init__(self, manager: ForceSensorManager, finger: Finger) -> None:
        self._manager = manager
        self._finger = finger

    @property
    def finger(self) -> Finger:
        """Finger that this reader is bound to."""
        return self._finger

    def get_blocking(self, timeout_ms: float = 1000) -> O20FingerForceData:
        """Read tactile data for this finger.

        Args:
            timeout_ms: Time to wait for each segment read.

        Returns:
            O20FingerForceData with the online flag and a 12x6 uint8 matrix.

        Raises:
            ValidationError: If timeout_ms is not positive.
            TimeoutError: If either segment does not arrive before the timeout.
            ProtocolError: If either segment payload is shorter than expected.
        """
        return self._manager._read_finger(self._finger, timeout_ms=timeout_ms)


class ForceSensorManager:
    """Manager for O20 tactile force sensor reads.

    Each finger is returned as a 12x6 uint8 matrix assembled from the front and
    back tactile registers. The all-finger snapshot is updated only by
    get_blocking(), not by single-finger reads.
    """

    def __init__(self, client: O20Client) -> None:
        """Initialize the force sensor manager.

        Args:
            client: O20 protocol client used for tactile register reads.
        """
        self._client = client
        self._relay = DataRelay[O20AllFingersData]()
        self._fingers: dict[Finger, FingerForceSensor] = {
            finger: FingerForceSensor(self, finger) for finger in Finger
        }

    def get_finger(self, finger: Finger) -> FingerForceSensor:
        """Return the per-finger reader bound to one finger.

        Args:
            finger: Finger to read.

        Returns:
            FingerForceSensor for the requested finger.
        """
        return self._fingers[finger]

    def get_blocking(self, timeout_ms: float = 1000) -> O20AllFingersData:
        """Read tactile data for all five fingers and update the snapshot.

        Args:
            timeout_ms: Time to wait for each segment read.

        Returns:
            O20AllFingersData containing one finger result per finger.

        Raises:
            ValidationError: If timeout_ms is not positive.
            TimeoutError: If any segment does not arrive before the timeout.
            ProtocolError: If any segment payload is shorter than expected.
        """
        if timeout_ms <= 0:
            raise ValidationError("timeout_ms must be positive")
        results = {
            finger: self._read_finger(finger, timeout_ms=timeout_ms)
            for finger in Finger
        }
        data = O20AllFingersData(
            thumb=results[Finger.THUMB],
            index=results[Finger.INDEX],
            middle=results[Finger.MIDDLE],
            ring=results[Finger.RING],
            pinky=results[Finger.PINKY],
            timestamp=time.time(),
        )
        self._relay.push(data)
        return data

    def get_snapshot(self) -> O20AllFingersData | None:
        """Return the latest cached all-finger tactile data."""
        return self._relay.snapshot()

    def _send_sense_request(self) -> None:
        self.get_blocking(timeout_ms=1000)

    def _set_event_sink(self, sink: Callable[[O20AllFingersData], None]) -> None:
        self._relay.set_sink(sink)

    def close(self) -> None:
        """Release any per-manager resources. The force sensor manager has none."""

    def _read_finger(self, finger: Finger, *, timeout_ms: float) -> O20FingerForceData:
        if timeout_ms <= 0:
            raise ValidationError("timeout_ms must be positive")
        register_data1, register_data2 = _FINGER_REGISTERS[finger]
        data1 = self._client.read(register=register_data1, timeout_ms=timeout_ms)
        data2 = self._client.read(register=register_data2, timeout_ms=timeout_ms)
        online, matrix = protocol.assemble_tactile_payload(data1, data2)
        values = (
            np.frombuffer(matrix, dtype=np.uint8)
            .copy()
            .reshape(protocol.O20_TACTILE_ROWS, protocol.O20_TACTILE_COLUMNS)
        )
        values.setflags(write=False)
        return O20FingerForceData(
            finger=finger, online=online, values=values, timestamp=time.time()
        )
