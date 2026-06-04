import pytest

from linkerbot.exceptions import ValidationError
from linkerbot.hand.l30 import percentages_to_raw as exported_percentages_to_raw
from linkerbot.hand.l30 import raw_to_percentages as exported_raw_to_percentages
from linkerbot.hand.l30.joints import (
    L30_JOINT_COUNT,
    L30_JOINT_SPECS,
    L30Angle,
    percentages_to_raw,
    raw_to_percentages,
    validate_u16_values,
)

pytestmark = [pytest.mark.l30, pytest.mark.canfd]


def test_joint_specs_match_l30_v2_ranges() -> None:
    assert len(L30_JOINT_SPECS) == L30_JOINT_COUNT
    assert L30_JOINT_SPECS[0].minimum == 0
    assert L30_JOINT_SPECS[0].maximum == 880
    assert L30_JOINT_SPECS[4].minimum == -200
    assert L30_JOINT_SPECS[4].maximum == 200
    assert L30_JOINT_SPECS[16].minimum == -900
    assert L30_JOINT_SPECS[16].maximum == 900


def test_l30_angle_round_trips_list_index_and_len() -> None:
    values = [spec.minimum for spec in L30_JOINT_SPECS]
    angle = L30Angle.from_list(values)

    assert angle.to_list() == values
    assert angle[0] == values[0]
    assert len(angle) == L30_JOINT_COUNT


def test_l30_angle_accepts_signed_joint_ranges() -> None:
    values = [spec.maximum for spec in L30_JOINT_SPECS]

    assert L30Angle.from_list(values).to_list() == values


def test_l30_angle_rejects_wrong_count() -> None:
    with pytest.raises(ValidationError, match="17"):
        L30Angle.from_list([0] * 16)


def test_l30_angle_rejects_wrong_type() -> None:
    values: list[int] = [spec.minimum for spec in L30_JOINT_SPECS]
    values[0] = 1.5  # type: ignore[list-item]

    with pytest.raises(ValidationError, match="int"):
        L30Angle.from_list(values)


def test_l30_angle_rejects_bool_values() -> None:
    values = [spec.minimum for spec in L30_JOINT_SPECS]
    values[0] = True

    with pytest.raises(ValidationError, match="int"):
        L30Angle.from_list(values)


def test_l30_angle_rejects_out_of_range() -> None:
    values = [spec.minimum for spec in L30_JOINT_SPECS]
    values[0] = 881

    with pytest.raises(ValidationError, match="880"):
        L30Angle.from_list(values)


def test_l30_angle_sensor_values_allow_out_of_command_range_readback() -> None:
    values = [spec.minimum for spec in L30_JOINT_SPECS]
    values[9] = -1

    assert L30Angle.from_sensor_values(values).to_list() == values


def test_validate_u16_values_checks_count_and_range() -> None:
    values = validate_u16_values(
        [60] * L30_JOINT_COUNT, name="torques", minimum=60, maximum=800
    )

    assert values == (60,) * L30_JOINT_COUNT
    with pytest.raises(ValidationError):
        validate_u16_values([60] * 16, name="torques", minimum=60, maximum=800)
    with pytest.raises(ValidationError):
        validate_u16_values([59] * 17, name="torques", minimum=60, maximum=800)


def test_percentages_convert_to_raw_using_each_joint_range() -> None:
    angle = percentages_to_raw([0] * L30_JOINT_COUNT)
    assert angle.to_list() == [spec.minimum for spec in L30_JOINT_SPECS]

    angle = percentages_to_raw([100] * L30_JOINT_COUNT)
    assert angle.to_list() == [spec.maximum for spec in L30_JOINT_SPECS]


def test_raw_to_percentages_converts_signed_ranges() -> None:
    angle = L30Angle.from_list([spec.minimum for spec in L30_JOINT_SPECS])

    assert raw_to_percentages(angle) == (0.0,) * L30_JOINT_COUNT


def test_percentage_helpers_are_exported_from_l30_package() -> None:
    angle = exported_percentages_to_raw([0] * L30_JOINT_COUNT)

    assert exported_raw_to_percentages(angle) == (0.0,) * L30_JOINT_COUNT


def test_percentages_reject_invalid_values() -> None:
    with pytest.raises(ValidationError):
        percentages_to_raw([101] * L30_JOINT_COUNT)
    with pytest.raises(ValidationError):
        percentages_to_raw([True] * L30_JOINT_COUNT)
