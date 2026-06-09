"""O20 CANFD protocol helpers.

This module contains the O20 29-bit extended frame ID layout, register address
constants, payload encoders/decoders, and DeviceInfo parsing used by the
transport-neutral O20 client.

The O20 protocol uses register read/write semantics on CANFD extended frames.
All multi-byte values are little-endian. The hand exposes 16 DOF, while the
on-wire register layout for joint vectors carries 17 slots (the 17th slot is a
reserved field that the SDK fills with zeros on writes and ignores on reads).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

from linkerbot.comm.canfd import CANFDMessage
from linkerbot.exceptions import CANError, ValidationError

O20_JOINT_COUNT = 16
O20_FRAME_VECTOR_COUNT = 17

O20_DEVICE_ID_RIGHT = 0x01
O20_DEVICE_ID_LEFT = 0x02
O20_DEVICE_ID_BOOTLOADER = 0x03
O20_DEVICE_ID_BROADCAST = 0xFF

O20_ACCESS_READ = 0
O20_ACCESS_WRITE = 1

O20_REG_DEVICE_INFO = 0x00
O20_REG_CALI_MODE = 0x01
O20_REG_ERROR_STATUS = 0x02
O20_REG_CURRENT_POS = 0x03
O20_REG_CURRENT_VEL = 0x04
O20_REG_CONFIG_STATUS = 0x05
O20_REG_TARGET_POS = 0x06
O20_REG_TARGET_VEL = 0x07
O20_REG_TARGET_TORQUE = 0x08
O20_REG_TACTILE_THUMB_DATA1 = 0x09
O20_REG_TACTILE_THUMB_DATA2 = 0x0A
O20_REG_TACTILE_INDEX_DATA1 = 0x0B
O20_REG_TACTILE_INDEX_DATA2 = 0x0C
O20_REG_TACTILE_MIDDLE_DATA1 = 0x0D
O20_REG_TACTILE_MIDDLE_DATA2 = 0x0E
O20_REG_TACTILE_RING_DATA1 = 0x0F
O20_REG_TACTILE_RING_DATA2 = 0x10
O20_REG_TACTILE_PINKY_DATA1 = 0x11
O20_REG_TACTILE_PINKY_DATA2 = 0x12
O20_REG_TEMP_DATA = 0x13
O20_REG_MOTOR_CURRENT = 0x15
O20_REG_JOINT_OFFSET = 0x16
O20_REG_OC_PROT = 0x20
O20_REG_OC_PROT_TIME = 0x21
O20_REG_SERIAL_NUMBER = 0x6E

O20_I16_VECTOR_BYTE_LENGTH = O20_FRAME_VECTOR_COUNT * 2
O20_U16_VECTOR_BYTE_LENGTH = O20_FRAME_VECTOR_COUNT * 2
O20_U8_VECTOR_BYTE_LENGTH = O20_FRAME_VECTOR_COUNT
O20_VECTOR_DLC = 0x0E
O20_U8_VECTOR_DLC = 0x0B
O20_EMPTY_REQUEST_DLC = 0x00

O20_DEVICE_INFO_BYTE_LENGTH = 62
O20_DEVICE_INFO_PRODUCT_LENGTH = 10
O20_DEVICE_INFO_SERIAL_LENGTH = 20
O20_DEVICE_INFO_SOFTWARE_LENGTH = 10
O20_DEVICE_INFO_HARDWARE_LENGTH = 10
O20_DEVICE_INFO_HAND_TYPE_LENGTH = 1
O20_DEVICE_INFO_UID_LENGTH = 11

O20_TACTILE_DATA1_LENGTH = 64
O20_TACTILE_DATA2_LENGTH = 9
O20_TACTILE_MATRIX_LENGTH = 72
O20_TACTILE_ROWS = 12
O20_TACTILE_COLUMNS = 6

O20_RESERVED_ID_MASK = 0x00000FFF
O20_DEVICE_ID_MAX = 0xFF
O20_REGISTER_MAX = 0xFF
O20_HAND_TYPE_LEFT = 0
O20_HAND_TYPE_RIGHT = 1

O20_FAULT_NONE = 0
O20_FAULT_OVER_TEMPERATURE = 1
O20_FAULT_OVER_CURRENT = 2
O20_FAULT_COMMUNICATION = 3
O20_FAULT_NOT_CALIBRATED = 4

_FAULT_MESSAGES = {
    O20_FAULT_NONE: "no fault",
    O20_FAULT_OVER_TEMPERATURE: "over temperature",
    O20_FAULT_OVER_CURRENT: "over current",
    O20_FAULT_COMMUNICATION: "communication error",
    O20_FAULT_NOT_CALIBRATED: "motor not calibrated",
}


class ProtocolError(CANError):
    """Raised when an O20 response violates the protocol or is malformed."""


class O20Register(IntEnum):
    """O20 application register addresses exposed by the SDK."""

    DEVICE_INFO = O20_REG_DEVICE_INFO
    ERROR_STATUS = O20_REG_ERROR_STATUS
    CURRENT_POS = O20_REG_CURRENT_POS
    CURRENT_VEL = O20_REG_CURRENT_VEL
    TARGET_POS = O20_REG_TARGET_POS
    TARGET_VEL = O20_REG_TARGET_VEL
    TARGET_TORQUE = O20_REG_TARGET_TORQUE
    TEMP_DATA = O20_REG_TEMP_DATA
    MOTOR_CURRENT = O20_REG_MOTOR_CURRENT


@dataclass(frozen=True, slots=True)
class O20FrameId:
    """Decoded fields of an O20 29-bit CANFD extended arbitration ID.

    The O20 protocol packs the device ID in bits 28..21, the register address
    in bits 20..13, and the read/write flag in bit 12. Bits 11..0 are reserved
    and must be zero on the wire.

    Attributes:
        device_id: 8-bit device ID identifying the hand controller.
        register: 8-bit register address being accessed.
        write: Read/write flag, 0 for read and 1 for write.
    """

    device_id: int
    register: int
    write: int

    def __post_init__(self) -> None:
        _validate_range(self.device_id, "device_id", 0, O20_DEVICE_ID_MAX)
        _validate_range(self.register, "register", 0, O20_REGISTER_MAX)
        _validate_range(self.write, "write", 0, 1)

    def to_int(self) -> int:
        """Pack the frame fields into a 29-bit O20 CANFD ID.

        Returns:
            Integer arbitration ID with reserved low bits cleared.
        """
        return build_can_id(
            device_id=self.device_id, register=self.register, write=bool(self.write)
        )


def build_can_id(*, device_id: int, register: int, write: bool) -> int:
    """Build an O20 29-bit CANFD arbitration ID.

    Args:
        device_id: 8-bit device ID identifying the hand controller.
        register: 8-bit register address being accessed.
        write: True for a write operation, False for a read.

    Returns:
        Packed 29-bit arbitration ID with bits 11..0 cleared.

    Raises:
        ValidationError: If device_id or register is outside its bit-width.
    """
    _validate_range(device_id, "device_id", 0, O20_DEVICE_ID_MAX)
    _validate_range(register, "register", 0, O20_REGISTER_MAX)
    return (device_id << 21) | (register << 13) | ((1 if write else 0) << 12)


def parse_can_id(arbitration_id: int) -> O20FrameId:
    """Parse an O20 29-bit CANFD arbitration ID.

    Args:
        arbitration_id: CANFD extended arbitration ID.

    Returns:
        Decoded O20FrameId.

    Raises:
        ValidationError: If the ID does not fit in 29 bits or uses reserved bits.
    """
    if arbitration_id < 0 or arbitration_id > 0x1FFFFFFF:
        raise ValidationError("O20 arbitration_id must fit in 29 bits")
    if arbitration_id & O20_RESERVED_ID_MASK:
        raise ValidationError("O20 arbitration_id reserved low bits must be zero")
    return O20FrameId(
        device_id=(arbitration_id >> 21) & O20_DEVICE_ID_MAX,
        register=(arbitration_id >> 13) & O20_REGISTER_MAX,
        write=(arbitration_id >> 12) & 0x1,
    )


def build_message(
    *,
    device_id: int,
    register: int,
    write: bool,
    data: bytes = b"",
    dlc: int | None = None,
    frame_type: int | None = None,
) -> CANFDMessage:
    """Build a CANFDMessage for one O20 protocol frame.

    Args:
        device_id: O20 device ID destination.
        register: O20 register address to access.
        write: True for register write, False for register read.
        data: Encoded register payload bytes. Empty for read requests.
        dlc: Optional CANFD DLC override. When omitted, the smallest DLC that
            fits the payload is selected by the CANFD message layer.
        frame_type: Optional CANFD frame type override.

    Returns:
        CANFDMessage with an extended O20 arbitration ID.
    """
    return CANFDMessage(
        arbitration_id=build_can_id(
            device_id=device_id, register=register, write=write
        ),
        data=data,
        dlc=dlc,
        is_extended_id=True,
        frame_type=frame_type,
    )


def encode_i16_vector(values: list[int] | tuple[int, ...]) -> bytes:
    """Encode 16 signed 16-bit motor values into the on-wire 17-slot frame.

    The O20 protocol carries 17 motor slots per joint vector. The SDK exposes
    16 DOF, so this encoder appends a single zeroed reserved slot to the end
    and packs every value as a little-endian signed int16.

    Args:
        values: 16 signed integer values for motors 1..16.

    Returns:
        34-byte little-endian payload with the trailing reserved slot zeroed.

    Raises:
        ValidationError: If the count, type, or int16 range is invalid.
    """
    _validate_vector_count(values)
    payload = bytearray(O20_I16_VECTOR_BYTE_LENGTH)
    for index, value in enumerate(values):
        _validate_range(value, "int16 value", -0x8000, 0x7FFF)
        payload[index * 2 : index * 2 + 2] = int(value).to_bytes(
            2, "little", signed=True
        )
    return bytes(payload)


def encode_u16_vector(
    values: list[int] | tuple[int, ...], *, minimum: int = 0, maximum: int = 0xFFFF
) -> bytes:
    """Encode 16 unsigned 16-bit motor values into the on-wire 17-slot frame.

    Args:
        values: 16 unsigned integer values for motors 1..16.
        minimum: Inclusive minimum accepted value.
        maximum: Inclusive maximum accepted value.

    Returns:
        34-byte little-endian payload with the trailing reserved slot zeroed.

    Raises:
        ValidationError: If the count, type, or value range is invalid.
    """
    _validate_vector_count(values)
    payload = bytearray(O20_U16_VECTOR_BYTE_LENGTH)
    for index, value in enumerate(values):
        _validate_range(value, "uint16 value", minimum, maximum)
        payload[index * 2 : index * 2 + 2] = int(value).to_bytes(
            2, "little", signed=False
        )
    return bytes(payload)


def encode_u8_vector(
    values: list[int] | tuple[int, ...], *, minimum: int = 0, maximum: int = 0xFF
) -> bytes:
    """Encode 16 unsigned 8-bit motor values into the on-wire 17-slot frame.

    Args:
        values: 16 unsigned byte values for motors 1..16.
        minimum: Inclusive minimum accepted value.
        maximum: Inclusive maximum accepted value.

    Returns:
        17-byte payload with the trailing reserved slot zeroed.

    Raises:
        ValidationError: If the count, type, or value range is invalid.
    """
    _validate_vector_count(values)
    payload = bytearray(O20_U8_VECTOR_BYTE_LENGTH)
    for index, value in enumerate(values):
        _validate_range(value, "uint8 value", minimum, maximum)
        payload[index] = int(value)
    return bytes(payload)


def decode_i16_vector_response(data: bytes) -> tuple[int, ...]:
    """Decode a 17-slot signed 16-bit register response and drop the reserved slot.

    Args:
        data: Raw register response payload, at least 34 bytes long.

    Returns:
        Tuple of 16 decoded signed integers for motors 1..16.

    Raises:
        ProtocolError: If the payload is shorter than the expected vector length.
    """
    if len(data) < O20_I16_VECTOR_BYTE_LENGTH:
        raise ProtocolError(
            f"i16 vector response too short: expected {O20_I16_VECTOR_BYTE_LENGTH} bytes, "
            f"got {len(data)}"
        )
    return tuple(
        int.from_bytes(data[index : index + 2], "little", signed=True)
        for index in range(0, O20_JOINT_COUNT * 2, 2)
    )


def decode_u16_vector_response(data: bytes) -> tuple[int, ...]:
    """Decode a 17-slot unsigned 16-bit register response and drop the reserved slot.

    Args:
        data: Raw register response payload, at least 34 bytes long.

    Returns:
        Tuple of 16 decoded unsigned integers for motors 1..16.

    Raises:
        ProtocolError: If the payload is shorter than the expected vector length.
    """
    if len(data) < O20_U16_VECTOR_BYTE_LENGTH:
        raise ProtocolError(
            f"u16 vector response too short: expected {O20_U16_VECTOR_BYTE_LENGTH} bytes, "
            f"got {len(data)}"
        )
    return tuple(
        int.from_bytes(data[index : index + 2], "little", signed=False)
        for index in range(0, O20_JOINT_COUNT * 2, 2)
    )


def decode_u8_vector_response(data: bytes) -> tuple[int, ...]:
    """Decode a 17-slot unsigned 8-bit register response and drop the reserved slot.

    Args:
        data: Raw register response payload, at least 17 bytes long.

    Returns:
        Tuple of 16 decoded byte values for motors 1..16.

    Raises:
        ProtocolError: If the payload is shorter than the expected vector length.
    """
    if len(data) < O20_U8_VECTOR_BYTE_LENGTH:
        raise ProtocolError(
            f"u8 vector response too short: expected {O20_U8_VECTOR_BYTE_LENGTH} bytes, "
            f"got {len(data)}"
        )
    return tuple(data[:O20_JOINT_COUNT])


def assemble_tactile_payload(data1: bytes, data2: bytes) -> tuple[bool, bytes]:
    """Assemble the 73-byte tactile block from the front and back register reads.

    The O20 tactile data block is 73 bytes long. Index 0 is the online flag and
    indices 1..72 are the 12x6 touch matrix. The hand splits this block into
    two registers per finger: a 64-byte front segment and a 9-byte back segment.

    Args:
        data1: Raw front-segment response, expected to be 64 bytes long.
        data2: Raw back-segment response, expected to be 9 bytes long.

    Returns:
        Tuple of online flag and the 72-byte tactile matrix payload.

    Raises:
        ProtocolError: If either segment is shorter than expected, or the online
            byte is outside the documented {0, 1} set.
    """
    if len(data1) < O20_TACTILE_DATA1_LENGTH:
        raise ProtocolError(
            f"tactile DATA1 too short: expected {O20_TACTILE_DATA1_LENGTH} bytes, "
            f"got {len(data1)}"
        )
    if len(data2) < O20_TACTILE_DATA2_LENGTH:
        raise ProtocolError(
            f"tactile DATA2 too short: expected {O20_TACTILE_DATA2_LENGTH} bytes, "
            f"got {len(data2)}"
        )
    online_byte = data1[0]
    if online_byte not in (0, 1):
        raise ProtocolError(
            f"unexpected tactile online flag 0x{online_byte:02X}: "
            f"protocol allows 0 (offline) or 1 (online) only"
        )
    matrix = data1[1:O20_TACTILE_DATA1_LENGTH] + data2[:O20_TACTILE_DATA2_LENGTH]
    return bool(online_byte), matrix


def fault_message(value: int) -> str:
    """Return a readable message for an O20 per-motor fault byte."""
    return _FAULT_MESSAGES.get(value, "unknown fault")


def _validate_vector_count(values: list[int] | tuple[int, ...]) -> None:
    if len(values) != O20_JOINT_COUNT:
        raise ValidationError(f"expected {O20_JOINT_COUNT} values, got {len(values)}")


def _validate_range(value: int, name: str, minimum: int, maximum: int) -> None:
    # Accept int subclasses (e.g. IntEnum) so callers can pass O20Register
    # members directly, but reject bool — True/False are int subclasses in
    # Python and would otherwise sneak through as 0/1.
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValidationError(f"{name} must be int")
    if value < minimum or value > maximum:
        raise ValidationError(f"{name} must be between {minimum} and {maximum}")
