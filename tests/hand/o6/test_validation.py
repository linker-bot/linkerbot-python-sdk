"""Unit tests for O6 data classes (no hardware required)."""

import pytest

from linkerbot.hand.o6 import (
    FaultCode,
    O6Acceleration,
    O6Angle,
    O6Fault,
    O6Speed,
    O6Torque,
)

pytestmark = [pytest.mark.o6, pytest.mark.validation]

JOINT_COUNT = 6
VALID_VALUES = [50.0] * JOINT_COUNT


class TestO6Angle:
    """Validate O6Angle construction, boundary, and round-trip."""

    def test_from_list_wrong_length_short(self):
        with pytest.raises(ValueError, match="Expected 6"):
            O6Angle.from_list([50.0] * 5)

    def test_from_list_wrong_length_long(self):
        with pytest.raises(ValueError, match="Expected 6"):
            O6Angle.from_list([50.0] * 7)

    def test_from_list_negative_value(self):
        with pytest.raises(ValueError, match="out of range"):
            O6Angle.from_list([-1.0] + [50.0] * 5)

    def test_from_list_over_100(self):
        with pytest.raises(ValueError, match="out of range"):
            O6Angle.from_list([101.0] + [50.0] * 5)

    def test_from_list_non_numeric(self):
        with pytest.raises(ValueError, match="must be float/int"):
            O6Angle.from_list(["a"] + [50.0] * 5)

    def test_round_trip(self):
        angle = O6Angle.from_list(VALID_VALUES)
        assert angle.to_list() == VALID_VALUES

    def test_getitem(self):
        angle = O6Angle.from_list(VALID_VALUES)
        for i in range(JOINT_COUNT):
            assert angle[i] == VALID_VALUES[i]

    def test_len(self):
        angle = O6Angle.from_list(VALID_VALUES)
        assert len(angle) == JOINT_COUNT

    def test_boundary_zero(self):
        angle = O6Angle.from_list([0.0] * JOINT_COUNT)
        assert angle.to_list() == [0.0] * JOINT_COUNT

    def test_boundary_one_hundred(self):
        angle = O6Angle.from_list([100.0] * JOINT_COUNT)
        assert angle.to_list() == [100.0] * JOINT_COUNT

    def test_getitem_out_of_range(self):
        angle = O6Angle.from_list(VALID_VALUES)
        with pytest.raises(IndexError):
            _ = angle[JOINT_COUNT]


class TestO6Speed:
    """Validate O6Speed construction and boundary."""

    def test_from_list_wrong_length(self):
        with pytest.raises(ValueError, match="Expected 6"):
            O6Speed.from_list([50.0] * 5)

    def test_from_list_negative_value(self):
        with pytest.raises(ValueError, match="out of range"):
            O6Speed.from_list([-1.0] + [50.0] * 5)

    def test_from_list_over_100(self):
        with pytest.raises(ValueError, match="out of range"):
            O6Speed.from_list([101.0] + [50.0] * 5)

    def test_from_list_non_numeric(self):
        with pytest.raises(ValueError, match="must be float/int"):
            O6Speed.from_list(["a"] + [50.0] * 5)

    def test_round_trip(self):
        speed = O6Speed.from_list(VALID_VALUES)
        assert speed.to_list() == VALID_VALUES

    def test_len(self):
        assert len(O6Speed.from_list(VALID_VALUES)) == JOINT_COUNT

    def test_boundary_zero(self):
        speed = O6Speed.from_list([0.0] * JOINT_COUNT)
        assert speed.to_list() == [0.0] * JOINT_COUNT

    def test_boundary_one_hundred(self):
        speed = O6Speed.from_list([100.0] * JOINT_COUNT)
        assert speed.to_list() == [100.0] * JOINT_COUNT


class TestO6Torque:
    """Validate O6Torque construction and boundary."""

    def test_from_list_wrong_length(self):
        with pytest.raises(ValueError, match="Expected 6"):
            O6Torque.from_list([50.0] * 5)

    def test_from_list_negative_value(self):
        with pytest.raises(ValueError, match="out of range"):
            O6Torque.from_list([-1.0] + [50.0] * 5)

    def test_from_list_over_100(self):
        with pytest.raises(ValueError, match="out of range"):
            O6Torque.from_list([101.0] + [50.0] * 5)

    def test_from_list_non_numeric(self):
        with pytest.raises(ValueError, match="must be float/int"):
            O6Torque.from_list(["a"] + [50.0] * 5)

    def test_round_trip(self):
        torque = O6Torque.from_list(VALID_VALUES)
        assert torque.to_list() == VALID_VALUES

    def test_len(self):
        assert len(O6Torque.from_list(VALID_VALUES)) == JOINT_COUNT


class TestO6Acceleration:
    """Validate O6Acceleration construction and boundary."""

    def test_from_list_wrong_length(self):
        with pytest.raises(ValueError, match="Expected 6"):
            O6Acceleration.from_list([50.0] * 5)

    def test_from_list_negative_value(self):
        with pytest.raises(ValueError, match="out of range"):
            O6Acceleration.from_list([-1.0] + [50.0] * 5)

    def test_from_list_over_100(self):
        with pytest.raises(ValueError, match="out of range"):
            O6Acceleration.from_list([101.0] + [50.0] * 5)

    def test_from_list_non_numeric(self):
        with pytest.raises(ValueError, match="must be float/int"):
            O6Acceleration.from_list(["a"] + [50.0] * 5)

    def test_round_trip(self):
        accel = O6Acceleration.from_list(VALID_VALUES)
        assert accel.to_list() == VALID_VALUES

    def test_len(self):
        assert len(O6Acceleration.from_list(VALID_VALUES)) == JOINT_COUNT

    def test_boundary_zero(self):
        accel = O6Acceleration.from_list([0.0] * JOINT_COUNT)
        assert accel.to_list() == [0.0] * JOINT_COUNT

    def test_boundary_one_hundred(self):
        accel = O6Acceleration.from_list([100.0] * JOINT_COUNT)
        assert accel.to_list() == [100.0] * JOINT_COUNT


class TestO6Fault:
    """Validate O6Fault construction and FaultCode operations."""

    def test_from_list_wrong_length(self):
        with pytest.raises(ValueError, match="Expected 6"):
            O6Fault.from_list([FaultCode.NONE] * 5)

    def test_round_trip(self):
        codes = [FaultCode.NONE] * JOINT_COUNT
        fault = O6Fault.from_list(codes)
        assert fault.to_list() == codes

    def test_len(self):
        fault = O6Fault.from_list([FaultCode.NONE] * JOINT_COUNT)
        assert len(fault) == JOINT_COUNT

    def test_has_any_fault_false(self):
        fault = O6Fault.from_list([FaultCode.NONE] * JOINT_COUNT)
        assert fault.has_any_fault() is False

    def test_has_any_fault_true(self):
        codes = [FaultCode.NONE] * JOINT_COUNT
        codes[0] = FaultCode.OVERCURRENT
        fault = O6Fault.from_list(codes)
        assert fault.has_any_fault() is True

    def test_getitem(self):
        codes = [FaultCode.NONE] * JOINT_COUNT
        codes[3] = FaultCode.OVERTEMPERATURE
        fault = O6Fault.from_list(codes)
        assert fault[3] == FaultCode.OVERTEMPERATURE


class TestFaultCode:
    """Validate O6 FaultCode enum methods."""

    def test_none_has_no_fault(self):
        assert FaultCode.NONE.has_fault() is False

    def test_single_fault_detected(self):
        assert FaultCode.OVERCURRENT.has_fault() is True

    def test_combined_faults(self):
        combined = FaultCode.OVERCURRENT | FaultCode.OVERTEMPERATURE
        assert combined.has_fault() is True

    def test_get_fault_names_none(self):
        assert FaultCode.NONE.get_fault_names() == ["No faults"]

    def test_get_fault_names_single(self):
        names = FaultCode.OVERCURRENT.get_fault_names()
        assert "Overcurrent" in names

    def test_get_fault_names_combined(self):
        combined = FaultCode.OVERCURRENT | FaultCode.OVERTEMPERATURE
        names = combined.get_fault_names()
        assert "Overcurrent" in names
        assert "Overtemperature" in names

    def test_all_fault_types(self):
        for code in [
            FaultCode.VOLTAGE_ABNORMAL,
            FaultCode.ENCODER_ABNORMAL,
            FaultCode.OVERTEMPERATURE,
            FaultCode.OVERCURRENT,
            FaultCode.OVERLOAD,
        ]:
            assert code.has_fault() is True
            assert len(code.get_fault_names()) == 1
