"""Unit tests for L20 data classes (no hardware required)."""

import pytest

from linkerbot.hand.l20 import (
    L20Angle,
    L20Fault,
    L20FaultCode,
    L20Speed,
    L20Torque,
)

pytestmark = [pytest.mark.l20, pytest.mark.validation]

JOINT_COUNT = 16
VALID_VALUES = [50.0] * JOINT_COUNT


class TestL20Angle:
    """Validate L20Angle construction, boundary, and round-trip."""

    def test_from_list_wrong_length_short(self):
        with pytest.raises(ValueError, match="Expected 16"):
            L20Angle.from_list([50.0] * 15)

    def test_from_list_wrong_length_long(self):
        with pytest.raises(ValueError, match="Expected 16"):
            L20Angle.from_list([50.0] * 17)

    def test_from_list_negative_value(self):
        with pytest.raises(ValueError, match="out of range"):
            L20Angle.from_list([-1.0] + [50.0] * 15)

    def test_from_list_over_100(self):
        with pytest.raises(ValueError, match="out of range"):
            L20Angle.from_list([101.0] + [50.0] * 15)

    def test_from_list_non_numeric(self):
        with pytest.raises(ValueError, match="must be float/int"):
            L20Angle.from_list(
                ["a"] + [50.0] * 15  # ty: ignore[invalid-argument-type]
            )

    def test_round_trip(self):
        angle = L20Angle.from_list(VALID_VALUES)
        assert angle.to_list() == VALID_VALUES

    def test_getitem(self):
        angle = L20Angle.from_list(VALID_VALUES)
        for i in range(JOINT_COUNT):
            assert angle[i] == VALID_VALUES[i]

    def test_len(self):
        angle = L20Angle.from_list(VALID_VALUES)
        assert len(angle) == JOINT_COUNT

    def test_getitem_out_of_range(self):
        angle = L20Angle.from_list(VALID_VALUES)
        with pytest.raises(IndexError):
            _ = angle[JOINT_COUNT]

    def test_boundary_zero(self):
        angle = L20Angle.from_list([0.0] * JOINT_COUNT)
        assert angle.to_list() == [0.0] * JOINT_COUNT

    def test_boundary_one_hundred(self):
        angle = L20Angle.from_list([100.0] * JOINT_COUNT)
        assert angle.to_list() == [100.0] * JOINT_COUNT


class TestL20Speed:
    """Validate L20Speed construction and boundary."""

    def test_from_list_wrong_length(self):
        with pytest.raises(ValueError, match="Expected 16"):
            L20Speed.from_list([50.0] * 15)

    def test_from_list_negative_value(self):
        with pytest.raises(ValueError, match="out of range"):
            L20Speed.from_list([-1.0] + [50.0] * 15)

    def test_from_list_over_100(self):
        with pytest.raises(ValueError, match="out of range"):
            L20Speed.from_list([101.0] + [50.0] * 15)

    def test_from_list_non_numeric(self):
        with pytest.raises(ValueError, match="must be float/int"):
            L20Speed.from_list(
                ["a"] + [50.0] * 15  # ty: ignore[invalid-argument-type]
            )

    def test_round_trip(self):
        speed = L20Speed.from_list(VALID_VALUES)
        assert speed.to_list() == VALID_VALUES

    def test_len(self):
        assert len(L20Speed.from_list(VALID_VALUES)) == JOINT_COUNT


class TestL20Torque:
    """Validate L20Torque construction and boundary."""

    def test_from_list_wrong_length(self):
        with pytest.raises(ValueError, match="Expected 16"):
            L20Torque.from_list([50.0] * 15)

    def test_from_list_negative_value(self):
        with pytest.raises(ValueError, match="out of range"):
            L20Torque.from_list([-1.0] + [50.0] * 15)

    def test_from_list_over_100(self):
        with pytest.raises(ValueError, match="out of range"):
            L20Torque.from_list([101.0] + [50.0] * 15)

    def test_from_list_non_numeric(self):
        with pytest.raises(ValueError, match="must be float/int"):
            L20Torque.from_list(
                ["a"] + [50.0] * 15  # ty: ignore[invalid-argument-type]
            )

    def test_round_trip(self):
        torque = L20Torque.from_list(VALID_VALUES)
        assert torque.to_list() == VALID_VALUES

    def test_len(self):
        assert len(L20Torque.from_list(VALID_VALUES)) == JOINT_COUNT


class TestL20Fault:
    """Validate L20Fault construction and L20FaultCode operations."""

    def test_from_list_wrong_length(self):
        with pytest.raises(ValueError, match="Expected 16"):
            L20Fault.from_list([L20FaultCode.NONE] * 15)

    def test_round_trip(self):
        codes = [L20FaultCode.NONE] * JOINT_COUNT
        fault = L20Fault.from_list(codes)
        assert fault.to_list() == codes

    def test_len(self):
        fault = L20Fault.from_list([L20FaultCode.NONE] * JOINT_COUNT)
        assert len(fault) == JOINT_COUNT

    def test_has_any_fault_false(self):
        fault = L20Fault.from_list([L20FaultCode.NONE] * JOINT_COUNT)
        assert fault.has_any_fault() is False

    def test_has_any_fault_true(self):
        codes = [L20FaultCode.NONE] * JOINT_COUNT
        codes[0] = L20FaultCode.MOTOR_OVER_CURRENT
        fault = L20Fault.from_list(codes)
        assert fault.has_any_fault() is True

    def test_getitem(self):
        codes = [L20FaultCode.NONE] * JOINT_COUNT
        codes[2] = L20FaultCode.OVER_TEMPERATURE
        fault = L20Fault.from_list(codes)
        assert fault[2] == L20FaultCode.OVER_TEMPERATURE


class TestL20FaultCode:
    """Validate L20FaultCode enum methods."""

    def test_none_has_no_fault(self):
        assert L20FaultCode.NONE.has_fault() is False

    def test_single_fault_detected(self):
        assert L20FaultCode.MOTOR_OVER_CURRENT.has_fault() is True

    def test_combined_faults(self):
        combined = L20FaultCode.MOTOR_OVER_CURRENT | L20FaultCode.OVER_TEMPERATURE
        assert combined.has_fault() is True

    def test_get_fault_names_none(self):
        assert L20FaultCode.NONE.get_fault_names() == ["No faults"]

    def test_get_fault_names_single(self):
        names = L20FaultCode.MOTOR_OVER_CURRENT.get_fault_names()
        assert "Motor overcurrent" in names

    def test_get_fault_names_combined(self):
        combined = L20FaultCode.MOTOR_OVER_CURRENT | L20FaultCode.OVER_TEMPERATURE
        names = combined.get_fault_names()
        assert "Motor overcurrent" in names
        assert "Overtemperature" in names

    def test_all_fault_types(self):
        for code in [
            L20FaultCode.MOTOR_ROTOR_LOCK,
            L20FaultCode.MOTOR_OVER_CURRENT,
            L20FaultCode.MOTOR_STALL_FAULT,
            L20FaultCode.VOLTAGE_ABNORMAL,
            L20FaultCode.SELF_CHECK_ABNORMAL,
            L20FaultCode.OVER_TEMPERATURE,
            L20FaultCode.SOFT_ROTOR_LOCK,
            L20FaultCode.MOTOR_COMM_ABNORMAL,
        ]:
            assert code.has_fault() is True
            assert len(code.get_fault_names()) == 1
