import pytest

from linkerbot.exceptions import ValidationError
from linkerbot.hand.l30.joints import (
    L30_JOINT_COUNT,
    L30_JOINT_SPECS,
    L30Angle,
    validate_raw_command_values,
    validate_u16_values,
)

pytestmark = [pytest.mark.l30, pytest.mark.canfd]


def test_joint_specs_match_l30_v6_left_hand_ranges() -> None:
    assert len(L30_JOINT_SPECS) == L30_JOINT_COUNT
    assert tuple(
        (spec.name, spec.minimum, spec.maximum) for spec in L30_JOINT_SPECS
    ) == (
        ("j1", 0, 900),
        ("j2", 0, 1200),
        ("j3", 0, 900),
        ("j4", 0, 800),
        ("j5", -200, 200),
        ("j6", 0, 1500),
        ("j7", 0, 1600),
        ("j8", 0, 1600),
        ("j9", 0, 1500),
        ("j10", 0, 1600),
        ("j11", 0, 1500),
        ("j12", -200, 200),
        ("j13", -200, 200),
        ("j14", -200, 200),
        ("j15", 0, 1600),
        ("j16", 0, 1500),
        ("j17", -1000, 1000),
    )


def test_l30_angle_stores_percentages_and_round_trips() -> None:
    percentages = [
        10.0,
        20.0,
        30.0,
        40.0,
        50.0,
        60.0,
        70.0,
        80.0,
        90.0,
        0.0,
        100.0,
        25.0,
        50.0,
        75.0,
        33.3,
        66.6,
        50.0,
    ]
    angle = L30Angle.from_list(percentages)

    assert angle.to_list() == percentages
    assert angle[0] == pytest.approx(10.0)
    assert len(angle) == L30_JOINT_COUNT


def test_l30_angle_percentage_boundaries_map_to_spec_range() -> None:
    zero_percent = L30Angle.from_list([0.0] * L30_JOINT_COUNT)
    assert zero_percent.to_raw() == [spec.minimum for spec in L30_JOINT_SPECS]

    full_percent = L30Angle.from_list([100.0] * L30_JOINT_COUNT)
    assert full_percent.to_raw() == [spec.maximum for spec in L30_JOINT_SPECS]


def test_l30_angle_fifty_percent_is_signed_joint_center() -> None:
    """For symmetric joints (J5/J12-J14/J17) 50 % must be the neutral 0."""
    midpoint = L30Angle.from_list([50.0] * L30_JOINT_COUNT)
    raw = midpoint.to_raw()

    for joint_index in (4, 11, 12, 13, 16):  # J5, J12, J13, J14, J17
        assert raw[joint_index] == 0


def test_l30_angle_rejects_wrong_count() -> None:
    with pytest.raises(ValidationError, match="17"):
        L30Angle.from_list([0.0] * 16)


def test_l30_angle_rejects_out_of_percentage_range() -> None:
    with pytest.raises(ValidationError, match="0 and 100"):
        L30Angle.from_list([101.0] * L30_JOINT_COUNT)
    with pytest.raises(ValidationError, match="0 and 100"):
        L30Angle.from_list([-0.1] * L30_JOINT_COUNT)


def test_l30_angle_rejects_non_numeric_percentage() -> None:
    values: list[float] = [0.0] * L30_JOINT_COUNT
    values[0] = "50"  # ty: ignore[invalid-assignment]
    with pytest.raises(ValidationError, match="float/int"):
        L30Angle.from_list(values)


def test_l30_angle_from_raw_round_trips_command_range() -> None:
    raws = [spec.maximum for spec in L30_JOINT_SPECS]
    angle = L30Angle.from_raw(raws)

    assert angle.to_list() == [100.0] * L30_JOINT_COUNT
    assert angle.to_raw() == raws


def test_l30_angle_from_raw_rejects_out_of_spec_range() -> None:
    raws = [spec.minimum for spec in L30_JOINT_SPECS]
    raws[0] = 901  # J1 max is 900

    with pytest.raises(ValidationError, match="900"):
        L30Angle.from_raw(raws)


def test_l30_angle_from_raw_rejects_non_int() -> None:
    values: list[int] = [spec.minimum for spec in L30_JOINT_SPECS]
    values[0] = 1.5  # ty: ignore[invalid-assignment]

    with pytest.raises(ValidationError, match="int"):
        L30Angle.from_raw(values)


def test_l30_angle_from_sensor_raw_allows_out_of_range() -> None:
    """Sensor readback may overshoot the documented command range."""
    raws = [spec.minimum for spec in L30_JOINT_SPECS]
    raws[9] = -1  # J10 minimum is 0, sensor returned -1

    angle = L30Angle.from_sensor_raw(raws)

    # Zero-percentage sanity: all-min raw values (except J10 which was -1)
    # produce 0 percent per joint; J10 should be slightly negative.
    assert angle.to_list()[0] == 0.0
    assert angle.to_list()[9] < 0


def test_validate_u16_values_checks_count_and_range() -> None:
    values = validate_u16_values(
        [60] * L30_JOINT_COUNT, name="torques", minimum=60, maximum=800
    )

    assert values == (60,) * L30_JOINT_COUNT
    with pytest.raises(ValidationError):
        validate_u16_values([60] * 16, name="torques", minimum=60, maximum=800)
    with pytest.raises(ValidationError):
        validate_u16_values([59] * 17, name="torques", minimum=60, maximum=800)


def test_validate_raw_command_values_matches_joint_specs() -> None:
    validated = validate_raw_command_values([spec.maximum for spec in L30_JOINT_SPECS])
    assert validated == tuple(spec.maximum for spec in L30_JOINT_SPECS)

    bad = [spec.maximum for spec in L30_JOINT_SPECS]
    bad[0] = 901
    with pytest.raises(ValidationError, match="900"):
        validate_raw_command_values(bad)
