"""L30 joint definitions and value models.

The public value type ``L30Angle`` follows the same convention as ``L6Angle``:
angle values are stored as **0-100 float percentages** in J1..J17 order. Raw
per-joint command integers (see ``L30_JOINT_SPECS`` for the documented ranges)
are only used at the ctypes-backend boundary. Users writing high-level code
should stay in the percentage space; drop to :meth:`L30Angle.from_raw` or
``AngleManager.set_raw_angles`` only when the raw protocol range is needed
(e.g. for reproducing a spec-boundary test).
"""

from __future__ import annotations

from dataclasses import dataclass

from linkerbot.exceptions import ValidationError

L30_JOINT_COUNT = 17


@dataclass(frozen=True, slots=True)
class JointSpec:
    """Documented raw command range for one L30 joint.

    Attributes:
        name: Joint name in protocol order.
        minimum: Minimum commandable raw angle value (protocol integer).
        maximum: Maximum commandable raw angle value (protocol integer).
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
    """L30 joint angles as 0-100 float percentages (aligned with ``L6Angle``).

    ``values`` is always 17 floats in J1..J17 order, each in the closed
    interval [0, 100]. 0 % maps to the joint's ``spec.minimum`` and 100 % to
    ``spec.maximum``. For symmetric joints (``J5``/``J12``-``J14``/``J17``)
    with negative minimums, 50 % is the neutral center.

    Sensor readback may legitimately fall slightly outside [0, 100] when the
    hardware calibrates or overshoots the documented command range; use
    :meth:`from_sensor_raw` for that path, which relaxes the range check.
    """

    values: tuple[float, ...]

    def __post_init__(self) -> None:
        _validate_percentage_values(self.values)

    @classmethod
    def from_list(cls, values: list[float] | tuple[float, ...]) -> L30Angle:
        """Construct from 0-100 percentage floats.

        Args:
            values: 17 percentage values in J1..J17 order, each in [0, 100].

        Returns:
            L30Angle command target.

        Raises:
            ValidationError: If count, type, or range is invalid.
        """
        # Pass through without coercion so a stray non-numeric (e.g. str) is
        # rejected by the type check in ``_validate_percentage_values``
        # rather than silently coerced by ``float(...)``.
        return cls(tuple(values))

    @classmethod
    def from_raw(cls, values: list[int] | tuple[int, ...]) -> L30Angle:
        """Construct from raw per-joint command integers (strict).

        Args:
            values: 17 raw integer values in J1..J17 order. Each must lie in
                its joint's documented ``[spec.minimum, spec.maximum]``.

        Returns:
            L30Angle with equivalent percentages.

        Raises:
            ValidationError: If count, type, or per-joint spec range is
                violated.
        """
        _validate_raw_command_values(tuple(values))
        percentages = tuple(
            _raw_to_percentage(value, spec)
            for value, spec in zip(values, L30_JOINT_SPECS, strict=True)
        )
        return cls(percentages)

    @classmethod
    def from_sensor_raw(cls, values: list[int] | tuple[int, ...]) -> L30Angle:
        """Construct from raw sensor readback (loose range check).

        Sensor readback may return values slightly outside the command range
        due to calibration or overshoot. This constructor only checks that
        the count is 17 and every value is ``int``; the resulting percentage
        may fall outside [0, 100] on individual joints.

        Args:
            values: 17 raw sensor integers in J1..J17 order.

        Returns:
            L30Angle whose ``values`` may include entries outside [0, 100].

        Raises:
            ValidationError: If count or per-value type is invalid.
        """
        _validate_sensor_raw_values(tuple(values))
        percentages = tuple(
            _raw_to_percentage(value, spec)
            for value, spec in zip(values, L30_JOINT_SPECS, strict=True)
        )
        # Bypass __post_init__ range check for sensor readback.
        angle = object.__new__(cls)
        object.__setattr__(angle, "values", percentages)
        return angle

    def to_list(self) -> list[float]:
        """Return angles as a mutable list of 0-100 floats in J1..J17 order."""
        return list(self.values)

    def to_raw(self) -> list[int]:
        """Convert to 17 raw per-joint command integers.

        Uses each joint's ``[spec.minimum, spec.maximum]`` range to map
        percentages back to protocol integers. For values inside [0, 100] the
        result is guaranteed to be inside the spec range; for sensor-derived
        angles whose percentage is outside [0, 100] the raw value may be
        outside the spec range (which is expected for sensor round-tripping).
        """
        return [
            round(spec.minimum + (spec.maximum - spec.minimum) * value / 100)
            for value, spec in zip(self.values, L30_JOINT_SPECS, strict=True)
        ]

    def __getitem__(self, index: int) -> float:
        """Return one angle by zero-based joint index."""
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


def validate_raw_command_values(
    values: list[int] | tuple[int, ...],
) -> tuple[int, ...]:
    """Validate raw command integers against each joint's spec range.

    Args:
        values: 17 raw integer values in J1..J17 order.

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
    for index, (value, spec) in enumerate(zip(values, L30_JOINT_SPECS, strict=True)):
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
