from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CanInterface:
    """Identifies the CAN bus a device is talking on."""

    interface_name: str
    interface_type: str
