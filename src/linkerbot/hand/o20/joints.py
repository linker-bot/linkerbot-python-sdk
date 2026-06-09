"""O20 joint definitions and value models.

The O20 hand exposes 16 commandable joints in motor-ID order. Joint ranges are
documented per finger and per axis; the protocol vector frame on the wire
carries 17 slots, but the SDK only exposes the first 16 to the user.
"""

from __future__ import annotations

from dataclasses import dataclass

from linkerbot.exceptions import ValidationError

O20_JOINT_COUNT = 16


@dataclass(frozen=True, slots=True)
class JointSpec:
    """Documented command range for one O20 joint.

    Attributes:
        name: Joint name in motor-ID order.
        finger: Finger that the joint belongs to.
        minimum: Minimum commandable raw angle value in degrees.
        maximum: Maximum commandable raw angle value in degrees.
    """

    name: str
    finger: str
    minimum: int
    maximum: int


O20_JOINT_SPECS: tuple[JointSpec, ...] = (
    JointSpec("thumb_mcp", "thumb", 0, 120),
    JointSpec("thumb_ip", "thumb", 0, 150),
    JointSpec("thumb_abd", "thumb", 0, 180),
    JointSpec("thumb_cmc", "thumb", 0, 130),
    JointSpec("index_abd", "index", -30, 30),
    JointSpec("index_mcp", "index", 0, 180),
    JointSpec("index_pip", "index", 0, 180),
    JointSpec("middle_abd", "middle", -30, 30),
    JointSpec("middle_mcp", "middle", 0, 180),
    JointSpec("middle_pip", "middle", 0, 180),
    JointSpec("ring_abd", "ring", -20, 20),
    JointSpec("ring_mcp", "ring", 0, 180),
    JointSpec("ring_pip", "ring", 0, 180),
    JointSpec("pinky_abd", "pinky", -20, 20),
    JointSpec("pinky_mcp", "pinky", 0, 180),
    JointSpec("pinky_dip", "pinky", 0, 180),
)


@dataclass(frozen=True, slots=True)
class O20Angle:
    """Raw O20 joint angles in motor-ID order.

    Use from_list() for command targets, which must stay inside the documented
    per-joint command ranges. Use from_sensor_values() for hardware readback,
    where calibrated sensor values can be outside the commandable range.

    Attributes:
        values: 16 raw integer angle values in motor-ID order (1..16).
    """

    values: tuple[int, ...]

    def __post_init__(self) -> None:
        _validate_angle_values(self.values)

    @classmethod
    def from_list(cls, values: list[int] | tuple[int, ...]) -> O20Angle:
        """Construct command-target angles with range validation.

        Args:
            values: 16 raw integer target angles in motor-ID order.

        Returns:
            O20Angle suitable for angle control commands.

        Raises:
            ValidationError: If count, type, or per-joint command range is invalid.
        """
        return cls(tuple(values))

    @classmethod
    def from_sensor_values(cls, values: list[int] | tuple[int, ...]) -> O20Angle:
        """Construct angles from hardware sensor readback.

        Sensor readback is validated for count and integer type only, because
        calibrated raw values can be outside the command range accepted by
        set_angles().

        Args:
            values: 16 raw integer sensor values in motor-ID order.

        Returns:
            O20Angle containing sensor readback values.

        Raises:
            ValidationError: If count or value type is invalid.
        """
        normalized = tuple(values)
        _validate_sensor_angle_values(normalized)
        angle = object.__new__(cls)
        object.__setattr__(angle, "values", normalized)
        return angle

    def to_list(self) -> list[int]:
        """Convert angles to a mutable list in motor-ID order.

        Returns:
            List of 16 raw integer angle values.
        """
        return list(self.values)

    def __getitem__(self, index: int) -> int:
        """Return one angle by zero-based joint index."""
        return self.values[index]

    def __len__(self) -> int:
        """Return the O20 joint count, always 16."""
        return O20_JOINT_COUNT


def validate_vector_count(
    values: list[int] | tuple[int, ...] | list[float] | tuple[float, ...],
    *,
    name: str,
) -> None:
    """Validate that a joint vector has exactly 16 values.

    Args:
        values: Joint-aligned values to validate.
        name: Human-readable value name used in error messages.

    Raises:
        ValidationError: If the vector length is not 16.
    """
    if len(values) != O20_JOINT_COUNT:
        raise ValidationError(f"{name} must contain {O20_JOINT_COUNT} values")


def validate_int_values(
    values: list[int] | tuple[int, ...],
    *,
    name: str,
    minimum: int,
    maximum: int,
) -> tuple[int, ...]:
    """Validate a 16-value integer command vector.

    Args:
        values: Raw integer values in motor-ID order.
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


def percentages_to_raw(values: list[float] | tuple[float, ...]) -> O20Angle:
    """Convert per-joint percentage targets to raw command angles.

    Args:
        values: 16 percentage values in motor-ID order, each between 0 and 100.

    Returns:
        O20Angle command target using each joint's documented raw range.

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
        spec = O20_JOINT_SPECS[index]
        raw_values.append(
            round(spec.minimum + (spec.maximum - spec.minimum) * value / 100)
        )
    return O20Angle.from_list(raw_values)


def raw_to_percentages(angle: O20Angle) -> tuple[float, ...]:
    """Convert raw command-range angles to per-joint percentages.

    Args:
        angle: O20Angle values to convert.

    Returns:
        Tuple of 16 percentage values in motor-ID order.
    """
    percentages: list[float] = []
    for value, spec in zip(angle.values, O20_JOINT_SPECS, strict=True):
        percentages.append((value - spec.minimum) * 100 / (spec.maximum - spec.minimum))
    return tuple(percentages)


def _validate_angle_values(values: tuple[int, ...]) -> None:
    validate_vector_count(values, name="angles")
    for index, (value, spec) in enumerate(zip(values, O20_JOINT_SPECS, strict=True)):
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
