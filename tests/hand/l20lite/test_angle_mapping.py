"""Unit tests for L20lite angle mapping (no hardware required)."""

from collections.abc import Callable
from pathlib import Path

import can
import pytest

from linkerbot.exceptions import ValidationError
from linkerbot.hand.l20lite.angle import AngleManager

pytestmark = [pytest.mark.l20lite, pytest.mark.validation]


class FakeDispatcher:
    def __init__(self) -> None:
        self.sent: list[can.Message] = []
        self.subscribers: list[Callable[[can.Message], None]] = []

    def subscribe(self, callback: Callable[[can.Message], None]) -> None:
        self.subscribers.append(callback)

    def send(self, msg: can.Message) -> None:
        self.sent.append(msg)


def _data(msg: can.Message) -> list[int]:
    return list(msg.data)


def _reverse_mapping(joint_count: int) -> list[list[int]]:
    return [list(reversed(range(256))) for _ in range(joint_count)]


def test_set_raw_angles_uses_default_linear_mapping(tmp_path: Path) -> None:
    dispatcher = FakeDispatcher()
    manager = AngleManager(0x28, dispatcher, tmp_path / "mapping.toml")

    manager.set_raw_angles(list(range(10)))

    assert [_data(msg) for msg in dispatcher.sent] == [
        [0x01, 0, 1, 2, 3, 4, 5],
        [0x04, 6, 7, 8, 9],
    ]


def test_set_raw_angles_uses_custom_mapping(tmp_path: Path) -> None:
    dispatcher = FakeDispatcher()
    manager = AngleManager(0x28, dispatcher, tmp_path / "mapping.toml")

    manager.set_angle_mapping(_reverse_mapping(10))
    manager.set_raw_angles(list(range(10)))

    assert [_data(msg) for msg in dispatcher.sent[-2:]] == [
        [0x01, 255, 254, 253, 252, 251, 250],
        [0x04, 249, 248, 247, 246],
    ]


def test_set_angles_converts_percentage_then_maps(tmp_path: Path) -> None:
    dispatcher = FakeDispatcher()
    manager = AngleManager(0x28, dispatcher, tmp_path / "mapping.toml")

    manager.set_angle_mapping(_reverse_mapping(10))
    manager.set_angles([0, 10, 20, 30, 40, 50, 60, 70, 80, 100])

    assert [_data(msg) for msg in dispatcher.sent[-2:]] == [
        [0x01, 255, 229, 204, 179, 153, 127],
        [0x04, 102, 77, 51, 0],
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
    left_can0.set_angle_mapping(_reverse_mapping(10))

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

    with pytest.raises(ValidationError):
        manager.set_raw_angles([0, 1, 2, 3, 4, 5, 6, 7, 8, 256])

    with pytest.raises(ValidationError):
        manager.set_raw_angles(
            [0, 1, 2, 3, 4, 5, 6, 7, 8, 9.0]  # ty: ignore[invalid-argument-type]
        )
