"""CANFD message types and DLC conversion helpers."""

from dataclasses import dataclass

from linkerbot.exceptions import ValidationError

CANFD_MAX_DATA_LENGTH = 64
CANFD_MAX_DLC = 15
CANFD_STANDARD_ID_MASK = 0x7FF
CANFD_EXTENDED_ID_MASK = 0x1FFFFFFF
CANFD_DEFAULT_NOMINAL_BAUD = 1_000_000
CANFD_DEFAULT_DATA_BAUD = 5_000_000
CANFD_DEFAULT_CONFIG_FLAGS = 0x01 | 0x02 | 0x04
CANFD_DEFAULT_MODEL = 0
CANFD_DEFAULT_CAN_TYPE = 1
CANFD_DEFAULT_FRAME_TYPE = 0x0C
_BYTE_MAX = 0xFF

_DLC_TO_LENGTH = {
    0: 0,
    1: 1,
    2: 2,
    3: 3,
    4: 4,
    5: 5,
    6: 6,
    7: 7,
    8: 8,
    9: 12,
    10: 16,
    11: 20,
    12: 24,
    13: 32,
    14: 48,
    15: 64,
}


def dlc_to_length(dlc: int) -> int:
    """Return the CANFD wire payload capacity for a DLC value."""
    if dlc not in _DLC_TO_LENGTH:
        raise ValidationError(f"dlc must be between 0 and {CANFD_MAX_DLC}")
    return _DLC_TO_LENGTH[dlc]


def length_to_dlc(length: int) -> int:
    """Return the smallest CANFD DLC capable of carrying length bytes."""
    if length < 0 or length > CANFD_MAX_DATA_LENGTH:
        raise ValidationError(
            f"CANFD payload length must be between 0 and {CANFD_MAX_DATA_LENGTH} bytes"
        )
    for dlc, capacity in _DLC_TO_LENGTH.items():
        if length <= capacity:
            return dlc
    raise ValidationError(
        f"CANFD payload length must be between 0 and {CANFD_MAX_DATA_LENGTH} bytes"
    )


@dataclass(frozen=True, slots=True)
class CANFDConfigOptions:
    """Configuration used when initializing the vendor CANFD adapter."""

    nom_baud: int = CANFD_DEFAULT_NOMINAL_BAUD
    dat_baud: int = CANFD_DEFAULT_DATA_BAUD
    config: int = CANFD_DEFAULT_CONFIG_FLAGS
    model: int = CANFD_DEFAULT_MODEL
    cantype: int = CANFD_DEFAULT_CAN_TYPE
    frame_type: int = CANFD_DEFAULT_FRAME_TYPE

    def __post_init__(self) -> None:
        if self.nom_baud <= 0:
            raise ValidationError("nom_baud must be positive")
        if self.dat_baud <= 0:
            raise ValidationError("dat_baud must be positive")
        _validate_byte(self.config, "config")
        _validate_byte(self.model, "model")
        _validate_byte(self.cantype, "cantype")
        _validate_byte(self.frame_type, "frame_type")


@dataclass(frozen=True, slots=True)
class CANFDMessage:
    """Immutable CANFD message used by the SDK's CANFD dispatcher."""

    arbitration_id: int
    data: bytes
    dlc: int | None = None
    is_extended_id: bool = True
    frame_type: int | None = None
    timestamp: int | None = None

    def __post_init__(self) -> None:
        data = bytes(self.data)
        if len(data) > CANFD_MAX_DATA_LENGTH:
            raise ValidationError(
                f"CANFD payload length must be between 0 and {CANFD_MAX_DATA_LENGTH} bytes"
            )

        if self.is_extended_id:
            _validate_id(self.arbitration_id, CANFD_EXTENDED_ID_MASK, "extended")
        else:
            _validate_id(self.arbitration_id, CANFD_STANDARD_ID_MASK, "standard")

        dlc = length_to_dlc(len(data)) if self.dlc is None else self.dlc
        if dlc < 0 or dlc > CANFD_MAX_DLC:
            raise ValidationError(f"dlc must be between 0 and {CANFD_MAX_DLC}")
        if len(data) > dlc_to_length(dlc):
            raise ValidationError("payload length exceeds explicit DLC capacity")

        if self.frame_type is not None:
            _validate_byte(self.frame_type, "frame_type")
        if self.timestamp is not None and self.timestamp < 0:
            raise ValidationError("timestamp must be non-negative")

        object.__setattr__(self, "data", data)
        object.__setattr__(self, "dlc", dlc)

    @classmethod
    def from_bytes(
        cls,
        *,
        arbitration_id: int,
        data: bytes | bytearray | memoryview,
        dlc: int | None = None,
        is_extended_id: bool = True,
        frame_type: int | None = None,
        timestamp: int | None = None,
    ) -> "CANFDMessage":
        """Create a CANFD message from any bytes-like payload."""
        return cls(
            arbitration_id=arbitration_id,
            data=bytes(data),
            dlc=dlc,
            is_extended_id=is_extended_id,
            frame_type=frame_type,
            timestamp=timestamp,
        )


def _validate_id(arbitration_id: int, max_value: int, name: str) -> None:
    if arbitration_id < 0 or arbitration_id > max_value:
        raise ValidationError(f"{name} arbitration_id must fit in 0x{max_value:X}")


def _validate_byte(value: int, name: str) -> None:
    if value < 0 or value > _BYTE_MAX:
        raise ValidationError(f"{name} must fit in one byte")
