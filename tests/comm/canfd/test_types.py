import pytest

from linkerbot.comm.canfd import CANFDConfigOptions, CANFDMessage
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
