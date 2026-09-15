"""Wire helpers for HandProtocol_v1.0, also known as HOP.

HOP is carried in standard CAN/CAN-FD frames. Each data field starts with a
three-byte header::

    CTRL | SI | EDL | payload...

``CTRL.bit7`` selects state versus set-point reads (RTS), ``CTRL.bit0..6`` is
the main index, ``SI`` is the byte offset inside the object, and ``EDL`` is the
effective object length. CAN-FD padding is deliberately excluded from EDL.
"""

from __future__ import annotations

from dataclasses import dataclass

from linkerbot.comm.canfd import CANFDMessage
from linkerbot.exceptions import CANError, ValidationError

HAND_PROTOCOL_RTS_MASK = 0x80
HAND_PROTOCOL_MAIN_INDEX_MASK = 0x7F
HAND_PROTOCOL_ERROR_MAIN_INDEX = 0x4F
HAND_PROTOCOL_DEFAULT_REQUEST_ID = 0x001
HAND_PROTOCOL_RESPONSE_ID_FLAG = 0x400
HAND_PROTOCOL_DEFAULT_RESPONSE_ID = 0x401
HAND_PROTOCOL_DEFAULT_FRAME_TYPE = 0x04  # CAN FD, no bit-rate switching.
HAND_PROTOCOL_HEADER_LENGTH = 3
HAND_PROTOCOL_MAX_FRAGMENT_LENGTH = 61
HAND_PROTOCOL_MAX_STANDARD_ID = 0x7FF
HAND_PROTOCOL_MAX_REQUEST_ID = 0x3FF

_DEVICE_ERROR_MESSAGES = {
    0x02: "sub-index does not exist or is out of range",
    0x40: "illegal data value",
}


class HandProtocolError(CANError):
    """Raised when a HOP response is malformed or violates a transaction."""


class HandProtocolDeviceError(HandProtocolError):
    """Error object returned by the device through main index ``0x4F``."""

    def __init__(self, *, error_index: int, error_code: int) -> None:
        self.error_index = error_index
        self.error_code = error_code
        description = _DEVICE_ERROR_MESSAGES.get(error_code, "unknown device error")
        super().__init__(
            f"HandProtocol device error 0x{error_code:02X} at index "
            f"0x{error_index:02X}: {description}"
        )


@dataclass(frozen=True, slots=True)
class HandProtocolFrame:
    """One decoded HOP response fragment without CAN-FD padding.

    Attributes:
        main_index: Seven-bit HOP main index.
        sub_index: Object byte offset carried in SI.
        payload: Exactly EDL useful bytes; any CAN-FD padding is discarded.
        rts: Whether CTRL.bit7 was set on the received frame.
    """

    main_index: int
    sub_index: int
    payload: bytes
    rts: bool = False

    @property
    def effective_length(self) -> int:
        """Number of useful payload bytes declared by EDL."""
        return len(self.payload)


def response_id_for_request(request_id: int) -> int:
    """Return the default HOP response ID for one standard request ID."""
    _validate_range(
        request_id,
        "request_id",
        0,
        HAND_PROTOCOL_MAX_REQUEST_ID,
    )
    return request_id | HAND_PROTOCOL_RESPONSE_ID_FLAG


def build_read_message(
    *,
    request_id: int,
    main_index: int,
    sub_index: int,
    length: int,
    rts: bool = False,
    frame_type: int | None = HAND_PROTOCOL_DEFAULT_FRAME_TYPE,
) -> CANFDMessage:
    """Build a three-byte HOP object-read request."""
    _validate_object_range(main_index, sub_index, length)
    _validate_standard_id(request_id, "request_id")
    _validate_frame_type(frame_type)
    control = main_index | (HAND_PROTOCOL_RTS_MASK if rts else 0)
    return CANFDMessage(
        arbitration_id=request_id,
        data=bytes((control, sub_index, length)),
        is_extended_id=False,
        frame_type=frame_type,
    )


def build_write_message(
    *,
    request_id: int,
    main_index: int,
    sub_index: int,
    payload: bytes,
    frame_type: int | None = HAND_PROTOCOL_DEFAULT_FRAME_TYPE,
) -> CANFDMessage:
    """Build a single-fragment HOP object-write request.

    HOP leaves 61 payload bytes after its three-byte header in a 64-byte CAN-FD
    frame. Larger object writes need a device-specific protocol extension and
    are intentionally rejected by this generic layer.
    """
    normalized = bytes(payload)
    if not normalized:
        raise ValidationError("HandProtocol write payload must not be empty")
    if len(normalized) > HAND_PROTOCOL_MAX_FRAGMENT_LENGTH:
        raise ValidationError(
            "HandProtocol write payload must contain at most "
            f"{HAND_PROTOCOL_MAX_FRAGMENT_LENGTH} bytes"
        )
    _validate_object_range(main_index, sub_index, len(normalized))
    _validate_standard_id(request_id, "request_id")
    _validate_frame_type(frame_type)
    return CANFDMessage(
        arbitration_id=request_id,
        data=bytes((main_index, sub_index, len(normalized))) + normalized,
        is_extended_id=False,
        frame_type=frame_type,
    )


def decode_frame(data: bytes) -> HandProtocolFrame:
    """Decode one HOP fragment and discard trailing CAN-FD padding."""
    normalized = bytes(data)
    if len(normalized) < HAND_PROTOCOL_HEADER_LENGTH:
        raise HandProtocolError(
            "HandProtocol frame too short: expected at least 3 header bytes"
        )
    control, sub_index, effective_length = normalized[:HAND_PROTOCOL_HEADER_LENGTH]
    required = HAND_PROTOCOL_HEADER_LENGTH + effective_length
    if len(normalized) < required:
        raise HandProtocolError(
            "HandProtocol payload shorter than EDL: "
            f"declared {effective_length}, received "
            f"{len(normalized) - HAND_PROTOCOL_HEADER_LENGTH}"
        )
    return HandProtocolFrame(
        main_index=control & HAND_PROTOCOL_MAIN_INDEX_MASK,
        sub_index=sub_index,
        payload=normalized[HAND_PROTOCOL_HEADER_LENGTH:required],
        rts=bool(control & HAND_PROTOCOL_RTS_MASK),
    )


def _validate_object_range(main_index: int, sub_index: int, length: int) -> None:
    _validate_range(
        main_index,
        "main_index",
        0,
        HAND_PROTOCOL_MAIN_INDEX_MASK,
    )
    _validate_range(sub_index, "sub_index", 0, 0xFF)
    _validate_range(length, "length", 1, 0xFF)
    if sub_index + length > 0x100:
        raise ValidationError("sub_index + length must not exceed 256")


def _validate_standard_id(arbitration_id: int, name: str) -> None:
    _validate_range(arbitration_id, name, 0, HAND_PROTOCOL_MAX_STANDARD_ID)


def _validate_frame_type(frame_type: int | None) -> None:
    if frame_type is not None:
        _validate_range(frame_type, "frame_type", 0, 0xFF)


def _validate_range(value: int, name: str, minimum: int, maximum: int) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValidationError(f"{name} must be int")
    if value < minimum or value > maximum:
        raise ValidationError(f"{name} must be between {minimum} and {maximum}")
