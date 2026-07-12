from __future__ import annotations

import pytest

from linkerbot.exceptions import ValidationError
from linkerbot.hand.o30i import (
    O30I_DEFAULT_RAW_VALUES,
    O30I_JOINT_COUNT,
    O30I_JOINT_SPECS,
    O30iAngle,
)

pytestmark = pytest.mark.o30i


def test_joint_table_exactly_matches_physical_o30i_layout() -> None:
    expected_ids = [
        "roll_0",
        "yaw_0",
        "yaw_1",
        "yaw_2",
        "yaw_3",
        "yaw_4",
        "root1_0",
        "root1_1",
        "root1_2",
        "root1_3",
        "root1_4",
        "root2_1",
        "root2_2",
        "root2_3",
        "root2_4",
        "tip_0",
        "tip_1",
        "tip_2",
        "tip_3",
        "tip_4",
    ]
    expected_names = [
        "拇指侧摆",
        "拇指横摆",
        "食指侧摆",
        "中指侧摆",
        "无名指侧摆",
        "小指侧摆",
        "拇指根 1",
        "食指根 1",
        "中指根 1",
        "无名指根 1",
        "小指根 1",
        "食指根 2",
        "中指根 2",
        "无名指根 2",
        "小指根 2",
        "拇指尖",
        "食指尖",
        "中指尖",
        "无名指尖",
        "小指尖",
    ]

    assert O30I_JOINT_COUNT == 20
    assert len(O30I_JOINT_SPECS) == 20
    assert [spec.id for spec in O30I_JOINT_SPECS] == expected_ids
    assert [spec.name for spec in O30I_JOINT_SPECS] == expected_names
    assert [spec.group for spec in O30I_JOINT_SPECS] == [
        "侧摆",
        "横滚",
        *(["侧摆"] * 4),
        *(["指根 1"] * 5),
        *(["指根 2"] * 4),
        *(["指尖"] * 5),
    ]
    assert [spec.wire_slot for spec in O30I_JOINT_SPECS] == [
        0,
        *range(5, 15),
        *range(16, 25),
    ]
    assert all(spec.minimum == 0 and spec.maximum == 255 for spec in O30I_JOINT_SPECS)


def test_joint_defaults_match_product_definition() -> None:
    assert O30I_DEFAULT_RAW_VALUES == (128, *([50] * 5), *([128] * 14))
    assert O30iAngle.defaults().to_raw() == list(O30I_DEFAULT_RAW_VALUES)


def test_joint_spec_serializes_to_application_json_shape() -> None:
    assert O30I_JOINT_SPECS[0].to_dict() == {
        "id": "roll_0",
        "name": "拇指侧摆",
        "min": 0,
        "max": 255,
        "default": 128,
        "group": "侧摆",
    }


@pytest.mark.parametrize("value", [-1, 256, True, 1.5])
def test_raw_angles_reject_values_outside_u8_contract(value: object) -> None:
    values: list[object] = [128] * 20
    values[7] = value
    with pytest.raises(ValidationError):
        O30iAngle.from_raw(values)


def test_angle_percentage_round_trip_uses_full_u8_range() -> None:
    angle = O30iAngle.from_list([0, 50, 100] + [25] * 17)

    raw = angle.to_raw()
    assert raw[:3] == [0, 128, 255]
    assert O30iAngle.from_raw(raw).to_raw() == raw


@pytest.mark.parametrize(
    "values, message",
    [
        ([0.0] * 19, "20 values"),
        ([0.0] * 19 + [101], "between 0 and 100"),
        ([0.0] * 19 + [True], "float/int"),
    ],
)
def test_angle_rejects_invalid_vectors(values: list[float], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        O30iAngle.from_list(values)
