"""Unit tests for L25 angle mapping (no hardware required)."""

from pathlib import Path

import pytest

from linkerbot.exceptions import ValidationError
from linkerbot.hand.l25.angle import AngleManager

pytestmark = [pytest.mark.l25, pytest.mark.validation]


class FakeDispatcher:
    def __init__(self) -> None:
        self.sent = []
        self.subscribers = []

    def subscribe(self, callback):
        self.subscribers.append(callback)

    def send(self, msg):
        self.sent.append(msg)


def _data(msg) -> list[int]:
    return list(msg.data)


def _reverse_mapping(joint_count: int) -> list[list[int]]:
    return [list(reversed(range(256))) for _ in range(joint_count)]


def test_set_raw_angles_uses_default_linear_mapping(tmp_path: Path) -> None:
    dispatcher = FakeDispatcher()
    manager = AngleManager(0x28, dispatcher, tmp_path / "mapping.toml")

    manager.set_raw_angles(list(range(16)))

    assert [_data(msg) for msg in dispatcher.sent] == [
        [0x41, 0, 1, 2, 0x00, 0x00, 3],
        [0x42, 4, 0x00, 5, 0x00, 0x00, 6],
        [0x43, 7, 0x00, 8, 0x00, 0x00, 9],
        [0x44, 10, 0x00, 11, 0x00, 0x00, 12],
        [0x45, 13, 0x00, 14, 0x00, 0x00, 15],
    ]


def test_set_raw_angles_uses_custom_mapping(tmp_path: Path) -> None:
    dispatcher = FakeDispatcher()
    manager = AngleManager(0x28, dispatcher, tmp_path / "mapping.toml")

    manager.set_angle_mapping(_reverse_mapping(16))
    manager.set_raw_angles(list(range(16)))

    assert [_data(msg) for msg in dispatcher.sent[-5:]] == [
        [0x41, 255, 254, 253, 0x00, 0x00, 252],
        [0x42, 251, 0x00, 250, 0x00, 0x00, 249],
        [0x43, 248, 0x00, 247, 0x00, 0x00, 246],
        [0x44, 245, 0x00, 244, 0x00, 0x00, 243],
        [0x45, 242, 0x00, 241, 0x00, 0x00, 240],
    ]


def test_set_angles_converts_percentage_then_maps(tmp_path: Path) -> None:
    dispatcher = FakeDispatcher()
    manager = AngleManager(0x28, dispatcher, tmp_path / "mapping.toml")

    manager.set_angle_mapping(_reverse_mapping(16))
    manager.set_angles([0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 0, 20, 40, 60, 80])

    assert [_data(msg) for msg in dispatcher.sent[-5:]] == [
        [0x41, 255, 229, 204, 0x00, 0x00, 179],
        [0x42, 153, 0x00, 127, 0x00, 0x00, 102],
        [0x43, 77, 0x00, 51, 0x00, 0x00, 25],
        [0x44, 0, 0x00, 255, 0x00, 0x00, 204],
        [0x45, 153, 0x00, 102, 0x00, 0x00, 51],
    ]


def test_mapping_is_persisted_by_side_and_interface(tmp_path: Path) -> None:
    path = tmp_path / "mapping.toml"
    left_can0 = AngleManager(
        0x28,
        FakeDispatcher(),
        path,
        side="left",
        interface_name="can0",
    )
    left_can0.set_angle_mapping(_reverse_mapping(16))

    right_can0 = AngleManager(
        0x27,
        FakeDispatcher(),
        path,
        side="right",
        interface_name="can0",
    )
    left_can1 = AngleManager(
        0x28,
        FakeDispatcher(),
        path,
        side="left",
        interface_name="can1",
    )

    assert left_can0.get_angle_mapping()[0][0] == 255
    assert right_can0.get_angle_mapping()[0][0] == 0
    assert left_can1.get_angle_mapping()[0][0] == 0


def test_set_raw_angles_rejects_invalid_values(tmp_path: Path) -> None:
    manager = AngleManager(0x28, FakeDispatcher(), tmp_path / "mapping.toml")

    with pytest.raises(ValidationError):
        manager.set_raw_angles([0, 1, 2])

    invalid = list(range(15)) + [256]
    with pytest.raises(ValidationError):
        manager.set_raw_angles(invalid)

    invalid_float = list(range(15)) + [15.0]
    with pytest.raises(ValidationError):
        manager.set_raw_angles(invalid_float)  # type: ignore[list-item]
