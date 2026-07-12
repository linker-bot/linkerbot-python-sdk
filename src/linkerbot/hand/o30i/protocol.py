"""O30i object indices and payload codecs for HandProtocol_v1.0.

The firmware exposes 36 one-byte runtime slots, but O30i physically implements
only 20 of them. State reads ask for the complete object and are projected onto
the physical-joint order. Writes are split around unimplemented wire slots so
commands never target joints that do not exist on the hand.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import IntEnum

from linkerbot.exceptions import ValidationError
from linkerbot.hand.hand_protocol_v1 import HandProtocolError

O30I_REQUEST_ID = 0x001
O30I_RESPONSE_ID = 0x401
O30I_FRAME_TYPE = 0x04

O30I_RUNTIME_SLOT_COUNT = 36
O30I_JOINT_SLOT_INDICES: tuple[int, ...] = (
    0,
    5,
    6,
    7,
    8,
    9,
    10,
    11,
    12,
    13,
    14,
    16,
    17,
    18,
    19,
    20,
    21,
    22,
    23,
    24,
)
O30I_CONTROLLED_JOINT_COUNT = len(O30I_JOINT_SLOT_INDICES)
O30I_U8_MIN = 0
O30I_U8_MAX = 0xFF
O30I_MAX_SPARSE_PAIRS = O30I_CONTROLLED_JOINT_COUNT

# Object 0x30 numbers joints by finger while dense objects group them by
# motion. This table is indexed by the 20-joint public SDK order.
O30I_JOINT_TO_SPARSE_JOINT_ID: tuple[int, ...] = (
    0,
    1,
    6,
    11,
    16,
    21,
    2,
    7,
    12,
    17,
    22,
    8,
    13,
    18,
    23,
    4,
    9,
    14,
    19,
    24,
)

O30I_MI_JOINT_MAPPING = 0x00
O30I_MI_POSITION = 0x01
O30I_MI_SPEED = 0x02
O30I_MI_ACCELERATION = 0x03
O30I_MI_CURRENT = 0x04
O30I_MI_VOLTAGE = 0x05
O30I_MI_TORQUE = 0x06
O30I_MI_TEMPERATURE = 0x07
O30I_MI_MOTION_TIME = 0x08
O30I_MI_STALL_TIME = 0x09
O30I_MI_STALL_THRESHOLD = 0x0A
O30I_MI_STALL_HOLD_CURRENT = 0x0B
O30I_MI_ENABLE_MASK = 0x0C
O30I_MI_FAULT = 0x0D
O30I_MI_POSITION_I16 = 0x20
O30I_MI_SPARSE_POSITION = 0x30
O30I_MI_SENSOR_INFO = 0x31
O30I_MI_SENSOR_DATA_1 = 0x32
O30I_MI_SENSOR_DATA_2 = 0x33
O30I_MI_SENSOR_DATA_3 = 0x34
O30I_MI_CONFIGURATION = 0x35
O30I_MI_PRODUCT_INFO = 0x41
O30I_MI_ENGINEERING = 0x42
O30I_MI_UNIT_RANGE = 0x43
O30I_MI_COMMUNICATION_ERROR = 0x4F

O30I_POSITION_I16_BYTE_LENGTH = O30I_RUNTIME_SLOT_COUNT * 2
O30I_PRODUCT_INFO_BYTE_LENGTH = 225
O30I_SENSOR_INFO_BYTE_LENGTH = 50
O30I_COMMUNICATION_ERROR_BYTE_LENGTH = 17


class O30iObject(IntEnum):
    """Measured HOP objects exposed by the O30i firmware."""

    POSITION = O30I_MI_POSITION
    SPEED = O30I_MI_SPEED
    ACCELERATION = O30I_MI_ACCELERATION
    CURRENT = O30I_MI_CURRENT
    VOLTAGE = O30I_MI_VOLTAGE
    TORQUE = O30I_MI_TORQUE
    TEMPERATURE = O30I_MI_TEMPERATURE
    MOTION_TIME = O30I_MI_MOTION_TIME
    STALL_TIME = O30I_MI_STALL_TIME
    STALL_THRESHOLD = O30I_MI_STALL_THRESHOLD
    STALL_HOLD_CURRENT = O30I_MI_STALL_HOLD_CURRENT
    FAULT = O30I_MI_FAULT
    POSITION_I16 = O30I_MI_POSITION_I16
    SPARSE_POSITION = O30I_MI_SPARSE_POSITION
    SENSOR_INFO = O30I_MI_SENSOR_INFO
    PRODUCT_INFO = O30I_MI_PRODUCT_INFO
    UNIT_RANGE = O30I_MI_UNIT_RANGE
    COMMUNICATION_ERROR = O30I_MI_COMMUNICATION_ERROR


def decode_runtime_vector(data: bytes) -> tuple[int, ...]:
    """Project a complete 36-slot object onto the 20 physical joints."""
    normalized = bytes(data)
    if len(normalized) < O30I_RUNTIME_SLOT_COUNT:
        raise HandProtocolError(
            "O30i runtime vector too short: expected "
            f"{O30I_RUNTIME_SLOT_COUNT} bytes, got {len(normalized)}"
        )
    return tuple(normalized[slot] for slot in O30I_JOINT_SLOT_INDICES)


def encode_control_vector(
    values: list[int] | tuple[int, ...],
) -> tuple[tuple[int, bytes], ...]:
    """Encode all physical joints as safe contiguous wire-slot writes."""
    normalized = _validate_u8_vector(
        values,
        name="values",
        expected_count=O30I_CONTROLLED_JOINT_COUNT,
    )
    return _encode_joint_slices(0, normalized)


def encode_control_slice(
    offset: int,
    values: list[int] | tuple[int, ...],
    *,
    name: str = "values",
) -> tuple[tuple[int, bytes], ...]:
    """Map a non-empty public-joint slice to contiguous wire-slot writes."""
    _validate_int(offset, "offset")
    if offset < 0 or offset >= O30I_CONTROLLED_JOINT_COUNT:
        raise ValidationError(
            f"offset must be between 0 and {O30I_CONTROLLED_JOINT_COUNT - 1}"
        )
    normalized = tuple(values)
    if not normalized:
        raise ValidationError(f"{name} must not be empty")
    if offset + len(normalized) > O30I_CONTROLLED_JOINT_COUNT:
        raise ValidationError(
            f"{name} slice must stay within the {O30I_CONTROLLED_JOINT_COUNT} "
            "physical O30i joints"
        )
    for index, value in enumerate(normalized):
        _validate_u8(value, f"{name}[{index}]")
    return _encode_joint_slices(offset, normalized)


def encode_sparse_positions(values: Mapping[int, int]) -> bytes:
    """Encode public SDK joint indices for sparse wire object ``0x30``.

    The mapping keys use the same 0..19 order as :data:`O30I_JOINT_SPECS` and
    are transposed to the firmware's finger-major sparse joint IDs.
    """
    if not isinstance(values, Mapping):
        raise ValidationError("sparse positions must be a mapping")
    if not values:
        raise ValidationError("sparse positions must not be empty")
    if len(values) > O30I_MAX_SPARSE_PAIRS:
        raise ValidationError(
            f"one sparse command supports at most {O30I_MAX_SPARSE_PAIRS} joints"
        )
    encoded_pairs: list[tuple[int, int]] = []
    for joint_index, value in sorted(values.items()):
        _validate_int(joint_index, "joint_index")
        if joint_index < 0 or joint_index >= O30I_CONTROLLED_JOINT_COUNT:
            raise ValidationError(
                "sparse joint_index must reference a physical joint 0..19"
            )
        _validate_u8(value, f"position[{joint_index}]")
        encoded_pairs.append((O30I_JOINT_TO_SPARSE_JOINT_ID[joint_index], value))
    payload = bytearray()
    for sparse_joint_id, value in sorted(encoded_pairs):
        payload.extend((sparse_joint_id, value))
    return bytes(payload)


def decode_i16_position_block(data: bytes) -> tuple[int, ...]:
    """Decode the full object and return its 20 physical-joint values."""
    normalized = bytes(data)
    if len(normalized) < O30I_POSITION_I16_BYTE_LENGTH:
        raise HandProtocolError(
            "O30i i16 position block too short: expected "
            f"{O30I_POSITION_I16_BYTE_LENGTH} bytes, got {len(normalized)}"
        )
    wire_values = tuple(
        int.from_bytes(normalized[index : index + 2], "little", signed=True)
        for index in range(0, O30I_POSITION_I16_BYTE_LENGTH, 2)
    )
    return tuple(wire_values[slot] for slot in O30I_JOINT_SLOT_INDICES)


def _encode_joint_slices(
    offset: int,
    values: tuple[int, ...],
) -> tuple[tuple[int, bytes], ...]:
    slices: list[tuple[int, bytes]] = []
    start_slot = O30I_JOINT_SLOT_INDICES[offset]
    payload = bytearray((values[0],))
    previous_slot = start_slot
    for joint_index, value in enumerate(values[1:], start=offset + 1):
        wire_slot = O30I_JOINT_SLOT_INDICES[joint_index]
        if wire_slot != previous_slot + 1:
            slices.append((start_slot, bytes(payload)))
            start_slot = wire_slot
            payload = bytearray()
        payload.append(value)
        previous_slot = wire_slot
    slices.append((start_slot, bytes(payload)))
    return tuple(slices)


def _validate_u8_vector(
    values: list[int] | tuple[int, ...],
    *,
    name: str,
    expected_count: int,
) -> tuple[int, ...]:
    normalized = tuple(values)
    if len(normalized) != expected_count:
        raise ValidationError(
            f"{name} must contain {expected_count} values, got {len(normalized)}"
        )
    for index, value in enumerate(normalized):
        _validate_u8(value, f"{name}[{index}]")
    return normalized


def _validate_u8(value: int, name: str) -> None:
    _validate_int(value, name)
    if value < O30I_U8_MIN or value > O30I_U8_MAX:
        raise ValidationError(f"{name} must be between 0 and 255")


def _validate_int(value: int, name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValidationError(f"{name} must be int")
