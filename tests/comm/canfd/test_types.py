from collections.abc import Callable

import pytest

from linkerbot.comm.canfd import (
    CANFDConfigOptions,
    CANFDMessage,
    dlc_to_length,
    length_to_dlc,
)
from linkerbot.exceptions import ValidationError


def test_message_auto_selects_dlc() -> None:
    message = CANFDMessage(arbitration_id=0x123, data=bytes(range(10)))

    assert message.dlc == 9
    assert message.data == bytes(range(10))


def test_message_allows_payload_shorter_than_explicit_dlc() -> None:
    message = CANFDMessage(arbitration_id=0x123, data=b"abc", dlc=8)

    assert message.dlc == 8


def test_message_rejects_payload_larger_than_explicit_dlc() -> None:
    with pytest.raises(ValidationError, match="payload length"):
        CANFDMessage(arbitration_id=0x123, data=bytes(range(9)), dlc=8)


def test_message_normalizes_bytes_like_payload() -> None:
    message = CANFDMessage.from_bytes(arbitration_id=0x123, data=bytearray([1, 2, 3]))

    assert message.data == b"\x01\x02\x03"


@pytest.mark.parametrize("data", [bytearray([1, 2]), memoryview(b"\x03\x04")])
def test_message_constructor_normalizes_bytes_like_payload(data: object) -> None:
    message = CANFDMessage(
        arbitration_id=0x123,
        data=data,  # ty: ignore[invalid-argument-type]
    )

    assert isinstance(message.data, bytes)
    assert message.data in (b"\x01\x02", b"\x03\x04")


@pytest.mark.parametrize("data", [3, "abc", [1, 2], object(), None])
def test_message_rejects_non_bytes_like_payload(data: object) -> None:
    with pytest.raises(ValidationError, match="data must be bytes-like"):
        CANFDMessage(
            arbitration_id=0x123,
            data=data,  # ty: ignore[invalid-argument-type]
        )


def test_message_wraps_invalid_memoryview_error() -> None:
    data = memoryview(b"abc")
    data.release()

    with pytest.raises(ValidationError, match="invalid bytes-like data"):
        CANFDMessage(
            arbitration_id=0x123,
            data=data,  # ty: ignore[invalid-argument-type]
        )


@pytest.mark.parametrize("arbitration_id", [0, 0x1FFFFFFF])
def test_message_accepts_extended_id_boundaries(arbitration_id: int) -> None:
    message = CANFDMessage(arbitration_id=arbitration_id, data=b"")

    assert message.arbitration_id == arbitration_id


def test_message_rejects_extended_id_overflow() -> None:
    with pytest.raises(ValidationError, match="extended"):
        CANFDMessage(arbitration_id=0x20000000, data=b"")


@pytest.mark.parametrize("arbitration_id", [0, 0x7FF])
def test_message_accepts_standard_id_boundaries(arbitration_id: int) -> None:
    message = CANFDMessage(
        arbitration_id=arbitration_id,
        data=b"",
        is_extended_id=False,
    )

    assert message.arbitration_id == arbitration_id


def test_message_rejects_standard_id_overflow() -> None:
    with pytest.raises(ValidationError, match="standard"):
        CANFDMessage(arbitration_id=0x800, data=b"", is_extended_id=False)


@pytest.mark.parametrize("field", ["config", "model", "cantype", "frame_type"])
def test_config_options_reject_byte_overflow(field: str) -> None:
    values = {field: 0x100}

    with pytest.raises(ValidationError):
        CANFDConfigOptions(**values)


def test_config_options_defaults_match_canfd_adapter_defaults() -> None:
    config = CANFDConfigOptions()

    assert config.nom_baud == 1_000_000
    assert config.dat_baud == 5_000_000
    assert config.config == 0x07
    assert config.model == 0
    assert config.cantype == 1
    assert config.frame_type == 0x0C


@pytest.mark.parametrize("converter", [dlc_to_length, length_to_dlc])
@pytest.mark.parametrize("value", [True, 1.0, float("nan"), "1", None, []])
def test_dlc_helpers_reject_non_integer_inputs(
    converter: Callable[[int], int], value: object
) -> None:
    with pytest.raises(ValidationError, match="must be int"):
        converter(value)  # ty: ignore[invalid-argument-type]


@pytest.mark.parametrize(
    "field",
    ["nom_baud", "dat_baud", "config", "model", "cantype", "frame_type"],
)
@pytest.mark.parametrize("value", [True, 1.5, float("nan"), "1", None])
def test_config_options_reject_non_integer_fields(field: str, value: object) -> None:
    with pytest.raises(ValidationError, match=field):
        CANFDConfigOptions(**{field: value})  # ty: ignore[invalid-argument-type]


@pytest.mark.parametrize("field", ["nom_baud", "dat_baud"])
@pytest.mark.parametrize("value", [0, -1, 2**32])
def test_config_options_reject_baud_outside_uint32(field: str, value: int) -> None:
    with pytest.raises(ValidationError, match="between 1"):
        CANFDConfigOptions(**{field: value})


@pytest.mark.parametrize(
    "field",
    ["arbitration_id", "dlc", "frame_type", "timestamp"],
)
@pytest.mark.parametrize("value", [True, 1.5, float("nan"), "1", []])
def test_message_rejects_non_integer_fields(field: str, value: object) -> None:
    values: dict[str, object] = {"arbitration_id": 1, "data": b""}
    values[field] = value

    with pytest.raises(ValidationError, match=field):
        CANFDMessage(**values)  # ty: ignore[invalid-argument-type]


@pytest.mark.parametrize("value", [0, 1, "true", None, []])
def test_message_rejects_non_boolean_extended_flag(value: object) -> None:
    with pytest.raises(ValidationError, match="is_extended_id must be bool"):
        CANFDMessage(
            arbitration_id=1,
            data=b"",
            is_extended_id=value,  # ty: ignore[invalid-argument-type]
        )
