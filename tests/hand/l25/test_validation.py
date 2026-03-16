"""Unit tests for L25 data classes (no hardware required)."""

import pytest

from linkerbot.hand.l25 import (
    L25Angle,
    L25Fault,
    L25FaultCode,
    L25Speed,
    L25Torque,
)

pytestmark = [pytest.mark.l25, pytest.mark.validation]

JOINT_COUNT = 16
VALID_VALUES = [50.0] * JOINT_COUNT


class TestL25Angle:
    """Validate L25Angle construction, boundary, and round-trip."""

    def test_from_list_wrong_length_short(self):
        with pytest.raises(ValueError, match="Expected 16"):
            L25Angle.from_list([50.0] * 15)

    def test_from_list_wrong_length_long(self):
        with pytest.raises(ValueError, match="Expected 16"):
            L25Angle.from_list([50.0] * 17)

    def test_from_list_negative_value(self):
        with pytest.raises(ValueError, match="out of range"):
            L25Angle.from_list([-1.0] + [50.0] * 15)

    def test_from_list_over_100(self):
        with pytest.raises(ValueError, match="out of range"):
            L25Angle.from_list([101.0] + [50.0] * 15)

    def test_from_list_non_numeric(self):
        with pytest.raises(ValueError, match="must be float/int"):
            L25Angle.from_list(["a"] + [50.0] * 15)

    def test_round_trip(self):
        angle = L25Angle.from_list(VALID_VALUES)
        assert angle.to_list() == VALID_VALUES

    def test_getitem(self):
        angle = L25Angle.from_list(VALID_VALUES)
        for i in range(JOINT_COUNT):
            assert angle[i] == VALID_VALUES[i]

    def test_len(self):
        angle = L25Angle.from_list(VALID_VALUES)
        assert len(angle) == JOINT_COUNT

    def test_getitem_out_of_range(self):
        angle = L25Angle.from_list(VALID_VALUES)
        with pytest.raises(IndexError):
            _ = angle[JOINT_COUNT]

    def test_boundary_zero(self):
        angle = L25Angle.from_list([0.0] * JOINT_COUNT)
        assert angle.to_list() == [0.0] * JOINT_COUNT

    def test_boundary_one_hundred(self):
        angle = L25Angle.from_list([100.0] * JOINT_COUNT)
        assert angle.to_list() == [100.0] * JOINT_COUNT


class TestL25Speed:
    """Validate L25Speed construction and boundary."""

    def test_from_list_wrong_length(self):
        with pytest.raises(ValueError, match="Expected 16"):
            L25Speed.from_list([50.0] * 15)

    def test_from_list_negative_value(self):
        with pytest.raises(ValueError, match="out of range"):
            L25Speed.from_list([-1.0] + [50.0] * 15)

    def test_from_list_over_100(self):
        with pytest.raises(ValueError, match="out of range"):
            L25Speed.from_list([101.0] + [50.0] * 15)

    def test_from_list_non_numeric(self):
        with pytest.raises(ValueError, match="must be float/int"):
            L25Speed.from_list(["a"] + [50.0] * 15)

    def test_round_trip(self):
        speed = L25Speed.from_list(VALID_VALUES)
        assert speed.to_list() == VALID_VALUES

    def test_len(self):
        assert len(L25Speed.from_list(VALID_VALUES)) == JOINT_COUNT


class TestL25Torque:
    """Validate L25Torque construction and boundary."""

    def test_from_list_wrong_length(self):
        with pytest.raises(ValueError, match="Expected 16"):
            L25Torque.from_list([50.0] * 15)

    def test_from_list_negative_value(self):
        with pytest.raises(ValueError, match="out of range"):
            L25Torque.from_list([-1.0] + [50.0] * 15)

    def test_from_list_over_100(self):
        with pytest.raises(ValueError, match="out of range"):
            L25Torque.from_list([101.0] + [50.0] * 15)

    def test_from_list_non_numeric(self):
        with pytest.raises(ValueError, match="must be float/int"):
            L25Torque.from_list(["a"] + [50.0] * 15)

    def test_round_trip(self):
        torque = L25Torque.from_list(VALID_VALUES)
        assert torque.to_list() == VALID_VALUES

    def test_len(self):
        assert len(L25Torque.from_list(VALID_VALUES)) == JOINT_COUNT


class TestL25Fault:
    """Validate L25Fault construction and L25FaultCode operations."""

    def test_from_list_wrong_length(self):
        with pytest.raises(ValueError, match="Expected 16"):
            L25Fault.from_list([L25FaultCode.NONE] * 15)

    def test_round_trip(self):
        codes = [L25FaultCode.NONE] * JOINT_COUNT
        fault = L25Fault.from_list(codes)
        assert fault.to_list() == codes

    def test_len(self):
        fault = L25Fault.from_list([L25FaultCode.NONE] * JOINT_COUNT)
        assert len(fault) == JOINT_COUNT

    def test_has_any_fault_false(self):
        fault = L25Fault.from_list([L25FaultCode.NONE] * JOINT_COUNT)
        assert fault.has_any_fault() is False

    def test_has_any_fault_true(self):
        codes = [L25FaultCode.NONE] * JOINT_COUNT
        codes[0] = L25FaultCode.MOTOR_OVER_CURRENT
        fault = L25Fault.from_list(codes)
        assert fault.has_any_fault() is True

    def test_getitem(self):
        codes = [L25FaultCode.NONE] * JOINT_COUNT
        codes[2] = L25FaultCode.OVER_TEMPERATURE
        fault = L25Fault.from_list(codes)
        assert fault[2] == L25FaultCode.OVER_TEMPERATURE


class TestL25FaultCode:
    """Validate L25FaultCode enum methods."""

    def test_none_has_no_fault(self):
        assert L25FaultCode.NONE.has_fault() is False

    def test_single_fault_detected(self):
        assert L25FaultCode.MOTOR_OVER_CURRENT.has_fault() is True

    def test_combined_faults(self):
        combined = L25FaultCode.MOTOR_OVER_CURRENT | L25FaultCode.OVER_TEMPERATURE
        assert combined.has_fault() is True

    def test_get_fault_names_none(self):
        assert L25FaultCode.NONE.get_fault_names() == ["No faults"]

    def test_get_fault_names_single(self):
        names = L25FaultCode.MOTOR_OVER_CURRENT.get_fault_names()
        assert "Motor overcurrent" in names

    def test_get_fault_names_combined(self):
        combined = L25FaultCode.MOTOR_OVER_CURRENT | L25FaultCode.OVER_TEMPERATURE
        names = combined.get_fault_names()
        assert "Motor overcurrent" in names
        assert "Overtemperature" in names

    def test_all_fault_types(self):
        for code in [
            L25FaultCode.MOTOR_ROTOR_LOCK,
            L25FaultCode.MOTOR_OVER_CURRENT,
            L25FaultCode.MOTOR_STALL_FAULT,
            L25FaultCode.VOLTAGE_ABNORMAL,
            L25FaultCode.SELF_CHECK_ABNORMAL,
            L25FaultCode.OVER_TEMPERATURE,
            L25FaultCode.SOFT_ROTOR_LOCK,
            L25FaultCode.MOTOR_COMM_ABNORMAL,
        ]:
            assert code.has_fault() is True
            assert len(code.get_fault_names()) == 1
