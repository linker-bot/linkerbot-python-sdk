"""O20 joint definitions and value models.

The public value type ``O20Angle`` follows the same convention as ``L6Angle``
and ``L30Angle``: angle values are stored as **0-100 float percentages** in
motor-ID order. Raw per-joint command integers (see ``O20_JOINT_SPECS`` for
the documented ranges) are only used at the ctypes-backend boundary. Users
writing high-level code should stay in the percentage space; drop to
:meth:`O20Angle.from_raw` or ``AngleManager.set_raw_angles`` only when the
raw protocol range is needed.
"""

from __future__ import annotations

from dataclasses import dataclass

from linkerbot.exceptions import ValidationError

O20_JOINT_COUNT = 16


@dataclass(frozen=True, slots=True)
class JointSpec:
    """Documented raw command range for one O20 joint.

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
    """O20 joint angles as 0-100 float percentages (aligned with ``L6Angle``
    and ``L30Angle``).

    ``values`` is always 16 floats in motor-ID order, each in the closed
    interval [0, 100]. 0 % maps to the joint's ``spec.minimum`` and 100 % to
    ``spec.maximum``. For abduction joints with negative minimums
    (index_abd / middle_abd / ring_abd / pinky_abd) 50 % is the neutral
    center.

    Sensor readback may legitimately fall slightly outside [0, 100] when the
    hardware calibrates or overshoots the documented command range; use
    :meth:`from_sensor_raw` for that path, which relaxes the range check.
    """

    values: tuple[float, ...]

    def __post_init__(self) -> None:
        _validate_percentage_values(self.values)

    @classmethod
    def from_list(cls, values: list[float] | tuple[float, ...]) -> O20Angle:
        """Construct from 0-100 percentage floats.

        Args:
            values: 16 percentage values in motor-ID order, each in [0, 100].

        Returns:
            O20Angle command target.

        Raises:
            ValidationError: If count, type, or range is invalid.
        """
        # Pass through without coercion so a stray non-numeric (e.g. str) is
        # rejected by the type check in ``_validate_percentage_values``
        # rather than silently coerced by ``float(...)``.
        return cls(tuple(values))

    @classmethod
    def from_raw(cls, values: list[int] | tuple[int, ...]) -> O20Angle:
        """Construct from raw per-joint command integers (strict).

        Args:
            values: 16 raw integer values in motor-ID order. Each must lie in
                its joint's documented ``[spec.minimum, spec.maximum]``.

        Returns:
            O20Angle with equivalent percentages.

        Raises:
            ValidationError: If count, type, or per-joint spec range is
                violated.
        """
        _validate_raw_command_values(tuple(values))
        percentages = tuple(
            _raw_to_percentage(value, spec)
            for value, spec in zip(values, O20_JOINT_SPECS, strict=True)
        )
        return cls(percentages)

    @classmethod
    def from_sensor_raw(cls, values: list[int] | tuple[int, ...]) -> O20Angle:
        """Construct from raw sensor readback (loose range check).

        Sensor readback may return values slightly outside the command range
        due to calibration or overshoot. This constructor only checks that
        the count is 16 and every value is ``int``; the resulting percentage
        may fall outside [0, 100] on individual joints.

        Args:
            values: 16 raw sensor integers in motor-ID order.

        Returns:
            O20Angle whose ``values`` may include entries outside [0, 100].

        Raises:
            ValidationError: If count or per-value type is invalid.
        """
        _validate_sensor_raw_values(tuple(values))
        percentages = tuple(
            _raw_to_percentage(value, spec)
            for value, spec in zip(values, O20_JOINT_SPECS, strict=True)
        )
        # Bypass __post_init__ range check for sensor readback.
        angle = object.__new__(cls)
        object.__setattr__(angle, "values", percentages)
        return angle

    def to_list(self) -> list[float]:
        """Return angles as a mutable list of 0-100 floats in motor-ID order."""
        return list(self.values)

    def to_raw(self) -> list[int]:
        """Convert to 16 raw per-joint command integers.

        Uses each joint's ``[spec.minimum, spec.maximum]`` range to map
        percentages back to protocol integers. For values inside [0, 100] the
        result is guaranteed to be inside the spec range; for sensor-derived
        angles whose percentage is outside [0, 100] the raw value may be
        outside the spec range (which is expected for sensor round-tripping).
        """
        return [
            round(spec.minimum + (spec.maximum - spec.minimum) * value / 100)
            for value, spec in zip(self.values, O20_JOINT_SPECS, strict=True)
        ]

    def __getitem__(self, index: int) -> float:
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


def validate_raw_command_values(
    values: list[int] | tuple[int, ...],
) -> tuple[int, ...]:
    """Validate raw command integers against each joint's spec range.

    Args:
        values: 16 raw integer values in motor-ID order.

    Returns:
        Normalized tuple.

    Raises:
        ValidationError: If count, type, or per-joint spec range is invalid.
    """
    _validate_raw_command_values(tuple(values))
    return tuple(values)


def _raw_to_percentage(value: int, spec: JointSpec) -> float:
    return (value - spec.minimum) * 100 / (spec.maximum - spec.minimum)


def _validate_percentage_values(values: tuple[float, ...]) -> None:
    validate_vector_count(values, name="angles")
    for index, value in enumerate(values):
        if type(value) not in (float, int):
            raise ValidationError(f"angles[{index}] must be float/int")
        if value < 0 or value > 100:
            raise ValidationError(
                f"angles[{index}] must be between 0 and 100, got {value}"
            )


def _validate_raw_command_values(values: tuple[int, ...]) -> None:
    validate_vector_count(values, name="raw_angles")
    for index, (value, spec) in enumerate(zip(values, O20_JOINT_SPECS, strict=True)):
        _validate_int(value, f"raw_angles[{index}]")
        if value < spec.minimum or value > spec.maximum:
            raise ValidationError(
                f"raw_angles[{index}] must be between "
                f"{spec.minimum} and {spec.maximum}, got {value}"
            )


def _validate_sensor_raw_values(values: tuple[int, ...]) -> None:
    validate_vector_count(values, name="sensor_angles")
    for index, value in enumerate(values):
        _validate_int(value, f"sensor_angles[{index}]")


def _validate_int(value: int, name: str) -> None:
    if type(value) is not int:
        raise ValidationError(f"{name} must be int")
