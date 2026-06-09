import pytest

from linkerbot.exceptions import ValidationError
from linkerbot.hand.o20.joints import (
    O20_JOINT_COUNT,
    O20_JOINT_SPECS,
    O20Angle,
    percentages_to_raw,
    raw_to_percentages,
    validate_int_values,
)

pytestmark = [pytest.mark.o20, pytest.mark.canfd]


def test_joint_specs_have_sixteen_entries_in_motor_id_order() -> None:
    assert len(O20_JOINT_SPECS) == 16
    assert O20_JOINT_SPECS[0].finger == "thumb"
    assert O20_JOINT_SPECS[15].finger == "pinky"


def test_o20_angle_from_list_validates_per_joint_command_range() -> None:
    values = [spec.minimum for spec in O20_JOINT_SPECS]
    angle = O20Angle.from_list(values)

    assert angle.to_list() == values
    assert len(angle) == O20_JOINT_COUNT


def test_o20_angle_from_list_rejects_out_of_range_values() -> None:
    values = [spec.minimum for spec in O20_JOINT_SPECS]
    values[0] = O20_JOINT_SPECS[0].maximum + 1

    with pytest.raises(ValidationError, match="angles"):
        O20Angle.from_list(values)


def test_o20_angle_from_sensor_values_accepts_out_of_range_readback() -> None:
    sensor_values = [O20_JOINT_SPECS[0].maximum + 50] + [0] * 15

    angle = O20Angle.from_sensor_values(sensor_values)

    assert angle.to_list() == sensor_values


def test_percentages_to_raw_uses_per_joint_minimum_and_maximum() -> None:
    angle = percentages_to_raw([50.0] * O20_JOINT_COUNT)

    expected = [
        round(spec.minimum + (spec.maximum - spec.minimum) * 0.5)
        for spec in O20_JOINT_SPECS
    ]
    assert angle.to_list() == expected


def test_percentages_to_raw_rejects_invalid_percentage() -> None:
    with pytest.raises(ValidationError):
        percentages_to_raw([101.0] * O20_JOINT_COUNT)
    with pytest.raises(ValidationError):
        percentages_to_raw([-1.0] * O20_JOINT_COUNT)


def test_raw_to_percentages_round_trips_for_minimum_and_maximum() -> None:
    minimums = [spec.minimum for spec in O20_JOINT_SPECS]
    maximums = [spec.maximum for spec in O20_JOINT_SPECS]

    assert raw_to_percentages(O20Angle.from_list(minimums)) == (0.0,) * 16
    assert raw_to_percentages(O20Angle.from_list(maximums)) == (100.0,) * 16


def test_validate_int_values_returns_normalized_tuple() -> None:
    values = validate_int_values([0] * 16, name="speeds", minimum=0, maximum=100)

    assert values == (0,) * 16


def test_validate_int_values_rejects_count_and_range() -> None:
    with pytest.raises(ValidationError):
        validate_int_values([0] * 15, name="speeds", minimum=0, maximum=100)
    with pytest.raises(ValidationError):
        validate_int_values([200] * 16, name="speeds", minimum=0, maximum=100)
