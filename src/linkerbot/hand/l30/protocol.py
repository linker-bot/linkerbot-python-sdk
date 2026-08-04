"""L30 CANFD protocol helpers.

This module contains the L30 v2 frame ID layout, payload encoders/decoders, and
response validation used by the transport-neutral L30 client.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

from linkerbot.comm.canfd import CANFDMessage
from linkerbot.exceptions import CANError, ValidationError

L30_JOINT_COUNT = 17
L30_PRIORITY_CONTROL = 0
L30_ACCESS_READ = 0
L30_ACCESS_WRITE = 1
L30_PARENT_CONTROL = 0x1
L30_PARENT_TACTILE = 0x2
L30_PARENT_CONFIG = 0x3
L30_PARENT_PERIODIC = 0x4
L30_PARENT_QUERY = 0x5
L30_SUBCMD_POSITION = 0x01
L30_SUBCMD_TORQUE = 0x02
L30_SUBCMD_CURRENT = 0x02
L30_SUBCMD_SPEED = 0x03
L30_SUBCMD_TEMPERATURE = 0x04
L30_SUBCMD_FAULT = 0x05
L30_SUBCMD_ENABLE = 0x07
L30_SUBCMD_DISABLE = 0x08
L30_SUBCMD_DEVICE_INFO = 0x02
L30_SUBCMD_PRODUCT_CODE = 0x03
L30_SUBCMD_NODE_ID = 0x04
L30_SUBCMD_HAND_TYPE = 0x06
L30_EMPTY_PAYLOAD_LENGTH = 0x00
L30_SINGLE_FRAME_TRANSACTION = 0x00
L30_STATUS_OK = 0x00
L30_STATUS_BYTE_INDEX = 2
L30_RESPONSE_DATA_OFFSET = 3
L30_ACK_DLC = 3
L30_EMPTY_REQUEST_DLC = 2
L30_VECTOR_BYTE_LENGTH = 34
L30_VECTOR_DLC = 0x0E
L30_U8_VECTOR_BYTE_LENGTH = 17
L30_U8_VECTOR_DLC = 0x0B
L30_DEVICE_INFO_BYTE_LENGTH = 18
L30_PERIODIC_CONFIG_BYTE_LENGTH = 9
L30_PERIODIC_CONFIG_DLC = 0x0A
L30_PERIODIC_MIN_PERIOD_MS = 20
L30_PERIODIC_MAX_PERIOD_MS = 600_000
L30_PERIODIC_ALL_JOINTS_MASK = 0x00000000
L30_JOINT_MASK_LIMIT = (1 << L30_JOINT_COUNT) - 1
L30_TACTILE_FIRST_FRAME_TRANSACTION = 0x10
L30_TACTILE_SECOND_FRAME_TRANSACTION = 0x11
L30_TACTILE_FIRST_FRAME_LENGTH = 61
L30_TACTILE_SECOND_FRAME_LENGTH = 11
L30_TACTILE_DATA_LENGTH = 72
L30_NODE_ID_MIN = 1
L30_NODE_ID_MAX = 31
L30_HOST_ID_MIN = 0
L30_HOST_ID_MAX = 31

_PRIORITY_MAX = 0x7
_ACCESS_MAX = 0x1
_PARENT_MAX = 0xF
_SUBCMD_MAX = 0xFF
_DEVICE_ID_MAX = 0x1F
_RESERVED_ID_MASK = 0x7

_STATUS_MESSAGES = {
    0x00: "success",
    0x10: "DLC or data length mismatch",
    0x11: "parameter out of range or illegal value",
    0x12: "unsupported command",
    0x13: "invalid subcommand",
    0x14: "data format error",
    0x20: "permission denied",
    0x21: "zero point not calibrated",
    0x22: "motor not enabled",
    0x23: "operation not allowed in current state",
    0x24: "device not configured",
    0x30: "motor data read error",
    0x31: "motor data write error",
    0x32: "multi-frame transfer timeout",
    0x33: "multi-frame data incomplete",
    0x34: "periodic report config failed",
    0x35: "periodic report period out of range",
    0x40: "communication timeout",
    0x41: "communication lost",
    0xF0: "system busy",
}


class ProtocolError(CANError):
    """Raised when an L30 response violates the protocol or reports an error."""


class SensorSubcommand(IntEnum):
    """L30 subcommands used by query and periodic sensor data."""

    POSITION = L30_SUBCMD_POSITION
    CURRENT = L30_SUBCMD_CURRENT
    SPEED = L30_SUBCMD_SPEED
    TEMPERATURE = L30_SUBCMD_TEMPERATURE
    FAULT = L30_SUBCMD_FAULT


@dataclass(frozen=True, slots=True)
class L30FrameId:
    """Decoded fields of an L30 29-bit CANFD extended arbitration ID.

    The L30 v2 response keeps the request Access bit and swaps source and
    destination IDs. This is why write ACKs still use Access=1.

    Attributes:
        priority: 3-bit priority field.
        access: 1-bit access field, 0 for read and 1 for write.
        parent: 4-bit parent command field.
        subcmd: 8-bit subcommand field.
        dst_id: 5-bit destination node ID.
        src_id: 5-bit source node ID.
    """

    priority: int
    access: int
    parent: int
    subcmd: int
    dst_id: int
    src_id: int

    def __post_init__(self) -> None:
        _validate_range(self.priority, "priority", 0, _PRIORITY_MAX)
        _validate_range(self.access, "access", 0, _ACCESS_MAX)
        _validate_range(self.parent, "parent", 0, _PARENT_MAX)
        _validate_range(self.subcmd, "subcmd", 0, _SUBCMD_MAX)
        _validate_range(self.dst_id, "dst_id", 0, _DEVICE_ID_MAX)
        _validate_range(self.src_id, "src_id", 0, _DEVICE_ID_MAX)

    def to_int(self) -> int:
        """Pack the frame fields into a 29-bit L30 CANFD ID.

        Returns:
            Integer arbitration ID with reserved low bits cleared.
        """
        return build_can_id(
            priority=self.priority,
            access=self.access,
            parent=self.parent,
            subcmd=self.subcmd,
            dst_id=self.dst_id,
            src_id=self.src_id,
        )

    def response(self) -> L30FrameId:
        """Return the expected response frame ID fields for this request.

        Returns:
            L30FrameId with destination/source IDs swapped and Access preserved.
        """
        return L30FrameId(
            priority=self.priority,
            access=self.access,
            parent=self.parent,
            subcmd=self.subcmd,
            dst_id=self.src_id,
            src_id=self.dst_id,
        )


def build_can_id(
    *,
    priority: int,
    access: int,
    parent: int,
    subcmd: int,
    dst_id: int,
    src_id: int,
) -> int:
    """Build an L30 29-bit CANFD arbitration ID.

    Args:
        priority: 3-bit priority field.
        access: Access field, 0 for read and 1 for write.
        parent: Parent command field.
        subcmd: Subcommand field.
        dst_id: Destination node ID.
        src_id: Source node ID.

    Returns:
        Packed 29-bit arbitration ID.

    Raises:
        ValidationError: If any field is outside its bit-width.
    """
    frame_id = L30FrameId(priority, access, parent, subcmd, dst_id, src_id)
    # L30 CANFD ID: priority|access|parent|subcmd|dst|src|reserved-low-3.
    return (
        (frame_id.priority << 26)
        | (frame_id.access << 25)
        | (frame_id.parent << 21)
        | (frame_id.subcmd << 13)
        | (frame_id.dst_id << 8)
        | (frame_id.src_id << 3)
    )


def parse_can_id(arbitration_id: int) -> L30FrameId:
    """Parse an L30 29-bit CANFD arbitration ID.

    Args:
        arbitration_id: CANFD extended arbitration ID.

    Returns:
        Decoded L30FrameId.

    Raises:
        ValidationError: If the ID does not fit in 29 bits or uses reserved bits.
    """
    if arbitration_id < 0 or arbitration_id > 0x1FFFFFFF:
        raise ValidationError("L30 arbitration_id must fit in 29 bits")
    if arbitration_id & _RESERVED_ID_MASK:
        raise ValidationError("L30 arbitration_id reserved low bits must be zero")
    return L30FrameId(
        priority=(arbitration_id >> 26) & _PRIORITY_MAX,
        access=(arbitration_id >> 25) & _ACCESS_MAX,
        parent=(arbitration_id >> 21) & _PARENT_MAX,
        subcmd=(arbitration_id >> 13) & _SUBCMD_MAX,
        dst_id=(arbitration_id >> 8) & _DEVICE_ID_MAX,
        src_id=(arbitration_id >> 3) & _DEVICE_ID_MAX,
    )


def expected_response_id(request_id: int) -> int:
    """Return the L30 v2 response arbitration ID for a request ID.

    Args:
        request_id: Packed request arbitration ID.

    Returns:
        Packed response arbitration ID with Access preserved and IDs swapped.
    """
    return parse_can_id(request_id).response().to_int()


def build_message(
    *,
    parent: int,
    subcmd: int,
    access: int,
    dst_id: int,
    src_id: int,
    data: bytes,
    dlc: int | None = None,
    frame_type: int | None = None,
) -> CANFDMessage:
    """Build a CANFDMessage for one L30 protocol frame.

    Args:
        parent: Parent command field.
        subcmd: Subcommand field.
        access: Access field, 0 for read and 1 for write.
        dst_id: Destination node ID.
        src_id: Source node ID.
        data: Encoded L30 payload.
        dlc: Optional CANFD DLC override.
        frame_type: Optional CANFD frame type override.

    Returns:
        CANFDMessage with an extended L30 arbitration ID.
    """
    return CANFDMessage(
        arbitration_id=build_can_id(
            priority=L30_PRIORITY_CONTROL,
            access=access,
            parent=parent,
            subcmd=subcmd,
            dst_id=dst_id,
            src_id=src_id,
        ),
        data=data,
        dlc=dlc,
        is_extended_id=True,
        frame_type=frame_type,
    )


def empty_request_payload() -> bytes:
    """Return the standard empty single-frame request payload."""
    return bytes([L30_EMPTY_PAYLOAD_LENGTH, L30_SINGLE_FRAME_TRANSACTION])


def ack_payload(status: int = L30_STATUS_OK) -> bytes:
    """Build a standard ACK payload for tests and fake dispatchers.

    Args:
        status: L30 status byte to include.

    Returns:
        Three-byte ACK payload.

    Raises:
        ValidationError: If status is not one byte.
    """
    _validate_range(status, "status", 0, 0xFF)
    return bytes([L30_EMPTY_PAYLOAD_LENGTH, L30_SINGLE_FRAME_TRANSACTION, status])


def encode_i16_vector(values: list[int] | tuple[int, ...]) -> bytes:
    """Encode a 17-value signed 16-bit L30 vector payload.

    Args:
        values: 17 signed integer values in J1..J17 order.

    Returns:
        Payload with L30 length/transaction header followed by big-endian i16s.

    Raises:
        ValidationError: If count or int16 range is invalid.
    """
    _validate_vector_count(values)
    payload = bytearray([L30_VECTOR_BYTE_LENGTH, L30_SINGLE_FRAME_TRANSACTION])
    for value in values:
        _validate_range(value, "int16 value", -0x8000, 0x7FFF)
        payload.extend(int(value).to_bytes(2, "big", signed=True))
    return bytes(payload)


def encode_u16_vector(
    values: list[int] | tuple[int, ...], *, minimum: int = 0, maximum: int = 0xFFFF
) -> bytes:
    """Encode a 17-value unsigned 16-bit L30 vector payload.

    Args:
        values: 17 unsigned integer values in J1..J17 order.
        minimum: Inclusive minimum accepted value.
        maximum: Inclusive maximum accepted value.

    Returns:
        Payload with L30 length/transaction header followed by big-endian u16s.

    Raises:
        ValidationError: If count or range is invalid.
    """
    _validate_vector_count(values)
    payload = bytearray([L30_VECTOR_BYTE_LENGTH, L30_SINGLE_FRAME_TRANSACTION])
    for value in values:
        _validate_range(value, "uint16 value", minimum, maximum)
        payload.extend(int(value).to_bytes(2, "big", signed=False))
    return bytes(payload)


def decode_i16_response(
    data: bytes, *, count: int = L30_JOINT_COUNT
) -> tuple[int, ...]:
    """Decode a status-checked signed 16-bit response vector.

    Args:
        data: Raw L30 response payload.
        count: Number of signed 16-bit values to decode.

    Returns:
        Tuple of decoded signed integers.

    Raises:
        ProtocolError: If status or payload length is invalid.
    """
    payload = _validate_response_header(data, expected_length=count * 2)
    return decode_i16_payload(payload, count=count)


def decode_u8_response(data: bytes, *, count: int = L30_JOINT_COUNT) -> tuple[int, ...]:
    """Decode a status-checked unsigned 8-bit response vector.

    Args:
        data: Raw L30 response payload.
        count: Number of bytes to decode.

    Returns:
        Tuple of decoded integer byte values.

    Raises:
        ProtocolError: If status or payload length is invalid.
    """
    payload = _validate_response_header(data, expected_length=count)
    return tuple(payload)


def decode_i16_payload(data: bytes, *, count: int) -> tuple[int, ...]:
    """Decode big-endian signed 16-bit payload values without status checking.

    Args:
        data: Raw bytes containing i16 values.
        count: Number of signed 16-bit values to decode.

    Returns:
        Tuple of decoded signed integers.

    Raises:
        ProtocolError: If data is shorter than the requested count.
    """
    byte_count = count * 2
    if len(data) < byte_count:
        raise ProtocolError(f"payload too short: expected {byte_count} bytes")
    return tuple(
        int.from_bytes(data[index : index + 2], "big", signed=True)
        for index in range(0, byte_count, 2)
    )


def encode_periodic_config(
    *, enabled: bool, period_ms: int = 0, joint_mask: int = L30_PERIODIC_ALL_JOINTS_MASK
) -> bytes:
    """Encode an L30 periodic report configuration payload.

    Args:
        enabled: Whether the periodic source should be enabled.
        period_ms: Report period in milliseconds, valid from 20 to 600000 when
            enabling reports.
        joint_mask: Joint selection mask. Zero means all joints in the L30 v2
            protocol.

    Returns:
        Encoded periodic configuration payload.

    Raises:
        ValidationError: If period_ms or joint_mask is invalid.
    """
    if enabled:
        _validate_range(
            period_ms,
            "period_ms",
            L30_PERIODIC_MIN_PERIOD_MS,
            L30_PERIODIC_MAX_PERIOD_MS,
        )
        _validate_joint_mask(joint_mask)
    else:
        period_ms = 0
        joint_mask = L30_PERIODIC_ALL_JOINTS_MASK
    return (
        bytes(
            [
                L30_PERIODIC_CONFIG_BYTE_LENGTH,
                L30_SINGLE_FRAME_TRANSACTION,
                0x01 if enabled else 0x00,
            ]
        )
        + period_ms.to_bytes(4, "big")
        + joint_mask.to_bytes(4, "big")
    )


def decode_periodic_i16_report(data: bytes, *, joint_mask: int) -> tuple[int, ...]:
    """Decode a signed 16-bit periodic report payload.

    Args:
        data: Raw periodic report payload.
        joint_mask: Joint mask used when the report source was configured.

    Returns:
        Tuple of signed report values.

    Raises:
        ProtocolError: If the report header or payload length is invalid.
    """
    count = _reported_joint_count(joint_mask)
    _validate_periodic_header(data, count * 2)
    return decode_i16_payload(data[2:], count=count)


def decode_periodic_u8_report(data: bytes, *, joint_mask: int) -> tuple[int, ...]:
    """Decode an unsigned 8-bit periodic report payload.

    Args:
        data: Raw periodic report payload.
        joint_mask: Joint mask used when the report source was configured.

    Returns:
        Tuple of report byte values.

    Raises:
        ProtocolError: If the report header or payload length is invalid.
    """
    count = _reported_joint_count(joint_mask)
    _validate_periodic_header(data, count)
    return tuple(data[2 : 2 + count])


def decode_response_payload(data: bytes, *, expected_length: int) -> bytes:
    """Return a strict status-checked response payload.

    Args:
        data: Raw L30 response payload with length, transaction, and status bytes.
        expected_length: Expected useful payload length declared by BYTE0.

    Returns:
        Useful payload bytes without the L30 response header or CANFD padding.

    Raises:
        ProtocolError: If response length, transaction, status, or payload bytes are invalid.
    """
    return _validate_response_header(data, expected_length=expected_length)


def decode_ascii_response(data: bytes) -> str:
    """Decode a strict status-checked ASCII response payload.

    Args:
        data: Raw L30 response payload with length, transaction, and status bytes.

    Returns:
        ASCII payload string without trailing NUL bytes.

    Raises:
        ProtocolError: If response validation fails or payload is not ASCII.
    """
    if not data:
        raise ProtocolError("response too short for length byte")
    payload = _validate_response_header(data, expected_length=data[0])
    try:
        return payload.rstrip(b"\x00").decode("ascii")
    except UnicodeDecodeError as error:
        raise ProtocolError("response payload is not valid ASCII") from error


def check_response_status(data: bytes) -> None:
    """Validate the standard L30 response status byte.

    Args:
        data: Raw response payload with length, transaction, and status bytes.

    Raises:
        ProtocolError: If the response is too short, has an unsupported
            transaction byte, or reports a non-zero status.
    """
    _validate_response_header(data, expected_length=L30_EMPTY_PAYLOAD_LENGTH)


def status_message(status: int) -> str:
    """Return a readable message for an L30 status byte."""
    return _STATUS_MESSAGES.get(status, "unknown status")


def _validate_response_header(data: bytes, *, expected_length: int) -> bytes:
    if len(data) <= L30_STATUS_BYTE_INDEX:
        raise ProtocolError("response too short for status byte")
    if data[0] != expected_length:
        raise ProtocolError(
            f"response length mismatch: expected {expected_length} bytes, got {data[0]}"
        )
    if data[1] != L30_SINGLE_FRAME_TRANSACTION:
        raise ProtocolError(f"unsupported transaction control 0x{data[1]:02X}")
    status = data[L30_STATUS_BYTE_INDEX]
    if status != L30_STATUS_OK:
        raise ProtocolError(f"L30 status 0x{status:02X}: {status_message(status)}")
    end = L30_RESPONSE_DATA_OFFSET + expected_length
    if len(data) < end:
        raise ProtocolError(
            f"response payload too short: expected {expected_length} bytes"
        )
    return data[L30_RESPONSE_DATA_OFFSET:end]


def assemble_tactile_payload(first_frame: bytes, second_frame: bytes) -> bytes:
    """Assemble the 72-byte tactile payload from two L30 response frames.

    The CANFD backend can deliver frames with DLC padding. The L30 tactile header
    declares the useful segment lengths, so this function slices exactly 61 bytes
    from the first frame and 11 bytes from the second frame.

    Args:
        first_frame: Tactile response frame with transaction 0x10.
        second_frame: Tactile response frame with transaction 0x11.

    Returns:
        72-byte tactile matrix payload without headers or padding.

    Raises:
        ProtocolError: If either frame has invalid status, transaction, declared
            length, or usable payload size.
    """
    _validate_tactile_frame(
        first_frame,
        transaction=L30_TACTILE_FIRST_FRAME_TRANSACTION,
        segment_length=L30_TACTILE_FIRST_FRAME_LENGTH,
    )
    _validate_tactile_frame(
        second_frame,
        transaction=L30_TACTILE_SECOND_FRAME_TRANSACTION,
        segment_length=L30_TACTILE_SECOND_FRAME_LENGTH,
    )
    first_payload = first_frame[
        L30_RESPONSE_DATA_OFFSET : L30_RESPONSE_DATA_OFFSET
        + L30_TACTILE_FIRST_FRAME_LENGTH
    ]
    second_payload = second_frame[
        L30_RESPONSE_DATA_OFFSET : L30_RESPONSE_DATA_OFFSET
        + L30_TACTILE_SECOND_FRAME_LENGTH
    ]
    payload = first_payload + second_payload
    if len(payload) != L30_TACTILE_DATA_LENGTH:
        raise ProtocolError("tactile payload length mismatch")
    return payload


def _validate_tactile_frame(
    data: bytes, *, transaction: int, segment_length: int
) -> None:
    if len(data) < L30_RESPONSE_DATA_OFFSET + segment_length:
        raise ProtocolError("tactile frame too short")
    if data[1] != transaction:
        raise ProtocolError(f"unexpected tactile transaction 0x{data[1]:02X}")
    status = data[L30_STATUS_BYTE_INDEX]
    if status != L30_STATUS_OK:
        raise ProtocolError(f"L30 status 0x{status:02X}: {status_message(status)}")
    if data[0] != segment_length:
        raise ProtocolError(f"unexpected tactile segment length {data[0]}")


def _validate_periodic_header(data: bytes, expected_length: int) -> None:
    if len(data) < 2 + expected_length:
        raise ProtocolError(
            f"periodic report too short: expected {expected_length} bytes"
        )
    if data[0] != expected_length:
        raise ProtocolError(f"periodic report length mismatch: got {data[0]}")
    if data[1] != L30_SINGLE_FRAME_TRANSACTION:
        raise ProtocolError(f"unsupported periodic transaction 0x{data[1]:02X}")


def _reported_joint_count(joint_mask: int) -> int:
    _validate_joint_mask(joint_mask)
    if joint_mask == L30_PERIODIC_ALL_JOINTS_MASK:
        return L30_JOINT_COUNT
    return joint_mask.bit_count()


def _validate_joint_mask(joint_mask: int) -> None:
    _validate_range(joint_mask, "joint_mask", 0, L30_JOINT_MASK_LIMIT)


def _validate_vector_count(values: list[int] | tuple[int, ...]) -> None:
    if len(values) != L30_JOINT_COUNT:
        raise ValidationError(f"expected {L30_JOINT_COUNT} values, got {len(values)}")


def _validate_range(value: int, name: str, minimum: int, maximum: int) -> None:
    if type(value) is not int:
        raise ValidationError(f"{name} must be int")
    if value < minimum or value > maximum:
        raise ValidationError(f"{name} must be between {minimum} and {maximum}")
