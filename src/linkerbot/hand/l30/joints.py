"""L30 joint definitions and value models."""

from __future__ import annotations

from dataclasses import dataclass

from linkerbot.exceptions import ValidationError

L30_JOINT_COUNT = 17


@dataclass(frozen=True, slots=True)
class JointSpec:
    """Documented command range for one L30 joint.

    Attributes:
        name: Joint name in protocol order.
        minimum: Minimum commandable raw angle value.
        maximum: Maximum commandable raw angle value.
    """

    name: str
    minimum: int
    maximum: int


L30_JOINT_SPECS: tuple[JointSpec, ...] = (
    JointSpec("j1", 0, 880),
    JointSpec("j2", 0, 1200),
    JointSpec("j3", 0, 900),
    JointSpec("j4", 0, 800),
    JointSpec("j5", -200, 200),
    JointSpec("j6", 0, 1200),
    JointSpec("j7", 0, 1200),
    JointSpec("j8", 0, 1200),
    JointSpec("j9", 0, 1200),
    JointSpec("j10", 0, 1500),
    JointSpec("j11", 0, 1200),
    JointSpec("j12", -200, 200),
    JointSpec("j13", -200, 200),
    JointSpec("j14", -200, 200),
    JointSpec("j15", 0, 1200),
    JointSpec("j16", 0, 1200),
    JointSpec("j17", -900, 900),
)


@dataclass(frozen=True, slots=True)
class L30Angle:
    """Raw L30 joint angles in protocol order.

    Use from_list() for command targets, which must stay inside the documented
    per-joint command ranges. Use from_sensor_values() for hardware readback,
    where calibrated sensor values can be outside the commandable range.

    Attributes:
        values: 17 raw integer angle values in J1..J17 order.
    """

    values: tuple[int, ...]

    def __post_init__(self) -> None:
        _validate_angle_values(self.values)

    @classmethod
    def from_list(cls, values: list[int] | tuple[int, ...]) -> L30Angle:
        """Construct command-target angles with range validation.

        Args:
            values: 17 raw integer target angles in J1..J17 order.

        Returns:
            L30Angle suitable for angle control commands.

        Raises:
            ValidationError: If count, type, or per-joint command range is invalid.
        """
        return cls(tuple(values))

    @classmethod
    def from_sensor_values(cls, values: list[int] | tuple[int, ...]) -> L30Angle:
        """Construct angles from hardware sensor readback.

        Sensor readback is validated for count and integer type only, because
        calibrated raw values can be outside the command range accepted by
        set_angles().

        Args:
            values: 17 raw integer sensor values in J1..J17 order.

        Returns:
            L30Angle containing sensor readback values.

        Raises:
            ValidationError: If count or value type is invalid.
        """
        normalized = tuple(values)
        _validate_sensor_angle_values(normalized)
        angle = object.__new__(cls)
        object.__setattr__(angle, "values", normalized)
        return angle

    def to_list(self) -> list[int]:
        """Convert angles to a mutable list in J1..J17 order.

        Returns:
            List of 17 raw integer angle values.
        """
        return list(self.values)

    def __getitem__(self, index: int) -> int:
        """Return one angle by zero-based joint index.

        Args:
            index: Zero-based joint index.

        Returns:
            Raw angle value for the joint.
        """
        return self.values[index]

    def __len__(self) -> int:
        """Return the L30 joint count, always 17."""
        return L30_JOINT_COUNT


def validate_vector_count(
    values: list[int] | tuple[int, ...] | list[float] | tuple[float, ...], *, name: str
) -> None:
    """Validate that a joint vector has exactly 17 values.

    Args:
        values: Joint-aligned values to validate.
        name: Human-readable value name used in error messages.

    Raises:
        ValidationError: If the vector length is not 17.
    """
    if len(values) != L30_JOINT_COUNT:
        raise ValidationError(f"{name} must contain {L30_JOINT_COUNT} values")


def validate_u16_values(
    values: list[int] | tuple[int, ...], *, name: str, minimum: int, maximum: int
) -> tuple[int, ...]:
    """Validate a 17-value unsigned integer command vector.

    Args:
        values: Raw integer values in J1..J17 order.
        name: Human-readable value name used in error messages.
        minimum: Inclusive minimum accepted value.
        maximum: Inclusive maximum accepted value.

    Returns:
        Normalized tuple of integer values.

    Raises:
        ValidationError: If count, type, or range is invalid.
    """
    validate_vector_count(values, name=name)
    normalized = tuple(values)
    for index, value in enumerate(normalized):
        _validate_int(value, f"{name}[{index}]")
        if value < minimum or value > maximum:
            raise ValidationError(
                f"{name}[{index}] must be between {minimum} and {maximum}"
            )
    return normalized


def percentages_to_raw(values: list[float] | tuple[float, ...]) -> L30Angle:
    """Convert per-joint percentage targets to raw command angles.

    Args:
        values: 17 percentage values in J1..J17 order, each between 0 and 100.

    Returns:
        L30Angle command target using each joint's documented raw range.

    Raises:
        ValidationError: If count, type, or percentage range is invalid.
    """
    validate_vector_count(values, name="percentages")
    raw_values: list[int] = []
    for index, value in enumerate(values):
        if type(value) not in (float, int):
            raise ValidationError(f"percentages[{index}] must be float/int")
        if value < 0 or value > 100:
            raise ValidationError(f"percentages[{index}] must be between 0 and 100")
        spec = L30_JOINT_SPECS[index]
        raw_values.append(
            round(spec.minimum + (spec.maximum - spec.minimum) * value / 100)
        )
    return L30Angle.from_list(raw_values)


def raw_to_percentages(angle: L30Angle) -> tuple[float, ...]:
    """Convert raw command-range angles to per-joint percentages.

    Args:
        angle: L30Angle values to convert.

    Returns:
        Tuple of 17 percentage values in J1..J17 order.
    """
    percentages: list[float] = []
    for value, spec in zip(angle.values, L30_JOINT_SPECS, strict=True):
        percentages.append((value - spec.minimum) * 100 / (spec.maximum - spec.minimum))
    return tuple(percentages)


def _validate_angle_values(values: tuple[int, ...]) -> None:
    validate_vector_count(values, name="angles")
    for index, (value, spec) in enumerate(zip(values, L30_JOINT_SPECS, strict=True)):
        _validate_int(value, f"angles[{index}]")
        if value < spec.minimum or value > spec.maximum:
            raise ValidationError(
                f"angles[{index}] must be between {spec.minimum} and {spec.maximum}"
            )


def _validate_sensor_angle_values(values: tuple[int, ...]) -> None:
    validate_vector_count(values, name="angles")
    for index, value in enumerate(values):
        _validate_int(value, f"angles[{index}]")


def _validate_int(value: int, name: str) -> None:
    if type(value) is not int:
        raise ValidationError(f"{name} must be int")
