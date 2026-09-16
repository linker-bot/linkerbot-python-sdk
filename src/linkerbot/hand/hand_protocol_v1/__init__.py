"""Transport-neutral implementation of ``HandProtocol_v1.0`` (HOP).

The package contains the reusable framing and transaction layer shared by
hands that implement the HOP object protocol. Device-specific packages, such
as :mod:`linkerbot.hand.o30`, define their supported main-index objects and
safe high-level operations on top of :class:`HandProtocolV1`.
"""

from .client import HandProtocolV1, HandProtocolV1DispatcherLike
from .protocol import (
    HAND_PROTOCOL_DEFAULT_FRAME_TYPE,
    HAND_PROTOCOL_DEFAULT_REQUEST_ID,
    HAND_PROTOCOL_DEFAULT_RESPONSE_ID,
    HAND_PROTOCOL_ERROR_MAIN_INDEX,
    HAND_PROTOCOL_MAX_FRAGMENT_LENGTH,
    HandProtocolDeviceError,
    HandProtocolError,
    HandProtocolFrame,
    build_read_message,
    build_write_message,
    decode_frame,
    response_id_for_request,
)

__all__ = [
    "HAND_PROTOCOL_DEFAULT_FRAME_TYPE",
    "HAND_PROTOCOL_DEFAULT_REQUEST_ID",
    "HAND_PROTOCOL_DEFAULT_RESPONSE_ID",
    "HAND_PROTOCOL_ERROR_MAIN_INDEX",
    "HAND_PROTOCOL_MAX_FRAGMENT_LENGTH",
    "HandProtocolDeviceError",
    "HandProtocolError",
    "HandProtocolFrame",
    "HandProtocolV1",
    "HandProtocolV1DispatcherLike",
    "build_read_message",
    "build_write_message",
    "decode_frame",
    "response_id_for_request",
]
