import pytest

from linkerbot.exceptions import ValidationError
from linkerbot.hand.o20.joints import (
    O20_JOINT_COUNT,
    O20_JOINT_SPECS,
    O20Angle,
    validate_int_values,
    validate_raw_command_values,
)

pytestmark = [pytest.mark.o20, pytest.mark.canfd]


def test_joint_specs_have_sixteen_entries_in_motor_id_order() -> None:
    assert len(O20_JOINT_SPECS) == 16
    assert O20_JOINT_SPECS[0].finger == "thumb"
    assert O20_JOINT_SPECS[15].finger == "pinky"
    assert O20_JOINT_SPECS[0].minimum == 0
    assert O20_JOINT_SPECS[0].maximum == 120
    assert O20_JOINT_SPECS[4].minimum == -30
    assert O20_JOINT_SPECS[4].maximum == 30


def test_o20_angle_stores_percentages_and_round_trips() -> None:
    percentages = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0,
                   0.0, 100.0, 25.0, 50.0, 75.0, 33.3, 66.6, 50.0]
    angle = O20Angle.from_list(percentages)

    assert angle.to_list() == percentages
    assert angle[0] == pytest.approx(10.0)
    assert len(angle) == O20_JOINT_COUNT


def test_o20_angle_percentage_boundaries_map_to_spec_range() -> None:
    zero_percent = O20Angle.from_list([0.0] * O20_JOINT_COUNT)
    assert zero_percent.to_raw() == [spec.minimum for spec in O20_JOINT_SPECS]

    full_percent = O20Angle.from_list([100.0] * O20_JOINT_COUNT)
    assert full_percent.to_raw() == [spec.maximum for spec in O20_JOINT_SPECS]


def test_o20_angle_fifty_percent_is_abduction_neutral() -> None:
    """For abduction joints (index_abd/middle_abd/ring_abd/pinky_abd) 50 %
    must map back to raw 0 (their symmetric neutral center)."""
    midpoint = O20Angle.from_list([50.0] * O20_JOINT_COUNT)
    raw = midpoint.to_raw()

    for joint_index in (4, 7, 10, 13):  # index/middle/ring/pinky abduction
        assert raw[joint_index] == 0


def test_o20_angle_rejects_wrong_count() -> None:
    with pytest.raises(ValidationError, match="16"):
        O20Angle.from_list([0.0] * 15)


def test_o20_angle_rejects_out_of_percentage_range() -> None:
    with pytest.raises(ValidationError, match="0 and 100"):
        O20Angle.from_list([101.0] * O20_JOINT_COUNT)
    with pytest.raises(ValidationError, match="0 and 100"):
        O20Angle.from_list([-0.1] * O20_JOINT_COUNT)


def test_o20_angle_rejects_non_numeric_percentage() -> None:
    values: list[float] = [0.0] * O20_JOINT_COUNT
    values[0] = "50"  # type: ignore[list-item]
    with pytest.raises(ValidationError, match="float/int"):
        O20Angle.from_list(values)


def test_o20_angle_from_raw_round_trips_command_range() -> None:
    raws = [spec.maximum for spec in O20_JOINT_SPECS]
    angle = O20Angle.from_raw(raws)

    assert angle.to_list() == [100.0] * O20_JOINT_COUNT
    assert angle.to_raw() == raws


def test_o20_angle_from_raw_rejects_out_of_spec_range() -> None:
    raws = [spec.minimum for spec in O20_JOINT_SPECS]
    raws[0] = 121  # thumb_mcp max is 120

    with pytest.raises(ValidationError, match="120"):
        O20Angle.from_raw(raws)


def test_o20_angle_from_raw_rejects_non_int() -> None:
    values: list[int] = [spec.minimum for spec in O20_JOINT_SPECS]
    values[0] = 1.5  # type: ignore[list-item]

    with pytest.raises(ValidationError, match="int"):
        O20Angle.from_raw(values)


def test_o20_angle_from_sensor_raw_allows_out_of_range() -> None:
    """Sensor readback may overshoot the documented command range."""
    raws = [spec.minimum for spec in O20_JOINT_SPECS]
    raws[0] = -5  # thumb_mcp minimum is 0

    angle = O20Angle.from_sensor_raw(raws)

    # Zero-percentage sanity: all-min raw values (except joint 0 which was -5)
    # produce 0 percent per joint; joint 0 should be slightly negative.
    assert angle.to_list()[1] == 0.0
    assert angle.to_list()[0] < 0


def test_validate_int_values_returns_normalized_tuple() -> None:
    values = validate_int_values([0] * 16, name="speeds", minimum=0, maximum=100)

    assert values == (0,) * 16


def test_validate_int_values_rejects_count_and_range() -> None:
    with pytest.raises(ValidationError):
        validate_int_values([0] * 15, name="speeds", minimum=0, maximum=100)
    with pytest.raises(ValidationError):
        validate_int_values([200] * 16, name="speeds", minimum=0, maximum=100)


def test_validate_raw_command_values_matches_joint_specs() -> None:
    validated = validate_raw_command_values(
        [spec.maximum for spec in O20_JOINT_SPECS]
    )
    assert validated == tuple(spec.maximum for spec in O20_JOINT_SPECS)

    bad = [spec.maximum for spec in O20_JOINT_SPECS]
    bad[0] = 121
    with pytest.raises(ValidationError, match="120"):
        validate_raw_command_values(bad)
