"""Unit tests for shared hand angle mapping helpers."""

from pathlib import Path

import pytest

from linkerbot.exceptions import ValidationError
from linkerbot.hand.angle_mapping import AngleMappingManager, default_angle_mapping


def _reverse_mapping(joint_count: int) -> list[list[int]]:
    return [list(reversed(range(256))) for _ in range(joint_count)]


def test_default_angle_mapping_is_linear() -> None:
    mapping = default_angle_mapping(6)

    assert len(mapping) == 6
    assert all(len(row) == 256 for row in mapping)
    assert mapping[0] == list(range(256))
    assert mapping[5] == list(range(256))


def test_mapping_manager_creates_default_toml(tmp_path: Path) -> None:
    path = tmp_path / "mappings.toml"

    manager = AngleMappingManager("l6", ["a", "b"], path)

    assert path.exists()
    assert manager.map_values([0, 255]) == [0, 255]
    assert manager.get_mapping() == [list(range(256)), list(range(256))]


def test_mapping_manager_preserves_other_model_sections(tmp_path: Path) -> None:
    path = tmp_path / "mappings.toml"
    l6 = AngleMappingManager("l6", ["a", "b"], path)
    custom = _reverse_mapping(2)
    l6.set_mapping(custom)

    l20 = AngleMappingManager("l20lite", ["c", "d", "e"], path)

    assert l20.map_values([1, 2, 3]) == [1, 2, 3]
    assert AngleMappingManager("l6", ["a", "b"], path).get_mapping() == custom


def test_mapping_manager_distinguishes_side_and_interface(tmp_path: Path) -> None:
    path = tmp_path / "mappings.toml"
    left_can0 = AngleMappingManager(
        "l6", ["a", "b"], path, side="left", interface_name="can0"
    )
    left_can0.set_mapping(_reverse_mapping(2))

    right_can0 = AngleMappingManager(
        "l6", ["a", "b"], path, side="right", interface_name="can0"
    )
    left_can1 = AngleMappingManager(
        "l6", ["a", "b"], path, side="left", interface_name="can1"
    )

    assert left_can0.map_values([0, 128]) == [255, 127]
    assert right_can0.map_values([0, 128]) == [0, 128]
    assert left_can1.map_values([0, 128]) == [0, 128]


def test_mapping_manager_reloads_saved_mapping(tmp_path: Path) -> None:
    path = tmp_path / "mappings.toml"
    manager = AngleMappingManager("l6", ["a", "b"], path)
    custom = _reverse_mapping(2)

    manager.set_mapping(custom)
    reloaded = AngleMappingManager("l6", ["a", "b"], path)

    assert reloaded.map_values([0, 128]) == [255, 127]


def test_mapping_manager_rejects_mismatched_joint_names(tmp_path: Path) -> None:
    path = tmp_path / "mappings.toml"
    AngleMappingManager("l6", ["a", "b"], path)

    with pytest.raises(ValidationError):
        AngleMappingManager("l6", ["b", "a"], path)


def test_mapping_manager_rejects_invalid_mapping(tmp_path: Path) -> None:
    manager = AngleMappingManager("l6", ["a", "b"], tmp_path / "mappings.toml")

    with pytest.raises(ValidationError):
        manager.set_mapping([[0] * 256])

    with pytest.raises(ValidationError):
        manager.set_mapping([[0] * 255, [0] * 256])

    invalid = default_angle_mapping(2)
    invalid[0][0] = 256
    with pytest.raises(ValidationError):
        manager.set_mapping(invalid)

    invalid = default_angle_mapping(2)
    invalid[0][0] = 1.0  # type: ignore[list-item]
    with pytest.raises(ValidationError):
        manager.set_mapping(invalid)


def test_mapping_manager_rejects_invalid_raw_values(tmp_path: Path) -> None:
    manager = AngleMappingManager("l6", ["a", "b"], tmp_path / "mappings.toml")

    with pytest.raises(ValidationError):
        manager.map_values([0])

    with pytest.raises(ValidationError):
        manager.map_values([0, 256])

    with pytest.raises(ValidationError):
        manager.map_values([0, 1.0])  # type: ignore[list-item]
