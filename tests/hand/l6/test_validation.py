"""Unit tests for L6 data classes (no hardware required)."""

import pytest

from linkerbot.hand.l6 import (
    FaultCode,
    L6Angle,
    L6Current,
    L6Fault,
    L6Speed,
    L6Torque,
)

pytestmark = [pytest.mark.l6, pytest.mark.validation]

JOINT_COUNT = 6
VALID_VALUES = [50.0] * JOINT_COUNT


class TestL6Angle:
    """Validate L6Angle construction, boundary, and round-trip."""

    def test_from_list_wrong_length_short(self):
        with pytest.raises(ValueError, match="Expected 6"):
            L6Angle.from_list([50.0] * 5)

    def test_from_list_wrong_length_long(self):
        with pytest.raises(ValueError, match="Expected 6"):
            L6Angle.from_list([50.0] * 7)

    def test_from_list_negative_value(self):
        with pytest.raises(ValueError, match="out of range"):
            L6Angle.from_list([-1.0] + [50.0] * 5)

    def test_from_list_over_100(self):
        with pytest.raises(ValueError, match="out of range"):
            L6Angle.from_list([101.0] + [50.0] * 5)

    def test_from_list_non_numeric(self):
        with pytest.raises(ValueError, match="must be float/int"):
            L6Angle.from_list(["a"] + [50.0] * 5)

    def test_round_trip(self):
        angle = L6Angle.from_list(VALID_VALUES)
        assert angle.to_list() == VALID_VALUES

    def test_getitem(self):
        angle = L6Angle.from_list(VALID_VALUES)
        for i in range(JOINT_COUNT):
            assert angle[i] == VALID_VALUES[i]

    def test_len(self):
        angle = L6Angle.from_list(VALID_VALUES)
        assert len(angle) == JOINT_COUNT

    def test_getitem_out_of_range(self):
        angle = L6Angle.from_list(VALID_VALUES)
        with pytest.raises(IndexError):
            _ = angle[JOINT_COUNT]

    def test_boundary_zero(self):
        angle = L6Angle.from_list([0.0] * JOINT_COUNT)
        assert angle.to_list() == [0.0] * JOINT_COUNT

    def test_boundary_one_hundred(self):
        angle = L6Angle.from_list([100.0] * JOINT_COUNT)
        assert angle.to_list() == [100.0] * JOINT_COUNT


class TestL6Speed:
    """Validate L6Speed construction and boundary."""

    def test_from_list_wrong_length(self):
        with pytest.raises(ValueError, match="Expected 6"):
            L6Speed.from_list([50.0] * 5)

    def test_from_list_negative_value(self):
        with pytest.raises(ValueError, match="out of range"):
            L6Speed.from_list([-1.0] + [50.0] * 5)

    def test_from_list_over_100(self):
        with pytest.raises(ValueError, match="out of range"):
            L6Speed.from_list([101.0] + [50.0] * 5)

    def test_from_list_non_numeric(self):
        with pytest.raises(ValueError, match="must be float/int"):
            L6Speed.from_list(["a"] + [50.0] * 5)

    def test_round_trip(self):
        speed = L6Speed.from_list(VALID_VALUES)
        assert speed.to_list() == VALID_VALUES

    def test_len(self):
        assert len(L6Speed.from_list(VALID_VALUES)) == JOINT_COUNT

    def test_boundary_zero(self):
        speed = L6Speed.from_list([0.0] * JOINT_COUNT)
        assert speed.to_list() == [0.0] * JOINT_COUNT

    def test_boundary_one_hundred(self):
        speed = L6Speed.from_list([100.0] * JOINT_COUNT)
        assert speed.to_list() == [100.0] * JOINT_COUNT


class TestL6Torque:
    """Validate L6Torque construction and boundary."""

    def test_from_list_wrong_length(self):
        with pytest.raises(ValueError, match="Expected 6"):
            L6Torque.from_list([50.0] * 5)

    def test_from_list_negative_value(self):
        with pytest.raises(ValueError, match="out of range"):
            L6Torque.from_list([-1.0] + [50.0] * 5)

    def test_from_list_over_100(self):
        with pytest.raises(ValueError, match="out of range"):
            L6Torque.from_list([101.0] + [50.0] * 5)

    def test_from_list_non_numeric(self):
        with pytest.raises(ValueError, match="must be float/int"):
            L6Torque.from_list(["a"] + [50.0] * 5)

    def test_round_trip(self):
        torque = L6Torque.from_list(VALID_VALUES)
        assert torque.to_list() == VALID_VALUES

    def test_len(self):
        assert len(L6Torque.from_list(VALID_VALUES)) == JOINT_COUNT


class TestL6Current:
    """Validate L6Current construction and round-trip.

    L6Current.from_list accepts any float values (mA units, no range restriction).
    """

    def test_from_list_wrong_length_short(self):
        with pytest.raises(ValueError, match="Expected 6"):
            L6Current.from_list([100.0] * 5)

    def test_from_list_wrong_length_long(self):
        with pytest.raises(ValueError, match="Expected 6"):
            L6Current.from_list([100.0] * 7)

    def test_round_trip(self):
        values = [100.0, 200.0, 300.0, 400.0, 500.0, 600.0]
        current = L6Current.from_list(values)
        assert current.to_list() == values

    def test_getitem(self):
        values = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0]
        current = L6Current.from_list(values)
        for i in range(JOINT_COUNT):
            assert current[i] == values[i]

    def test_len(self):
        current = L6Current.from_list([0.0] * JOINT_COUNT)
        assert len(current) == JOINT_COUNT

    def test_zero_values(self):
        current = L6Current.from_list([0.0] * JOINT_COUNT)
        assert current.to_list() == [0.0] * JOINT_COUNT


class TestL6Fault:
    """Validate L6Fault construction and FaultCode operations."""

    def test_from_list_wrong_length(self):
        with pytest.raises(ValueError, match="Expected 6"):
            L6Fault.from_list([FaultCode.NONE] * 5)

    def test_round_trip(self):
        codes = [FaultCode.NONE] * JOINT_COUNT
        fault = L6Fault.from_list(codes)
        assert fault.to_list() == codes

    def test_len(self):
        fault = L6Fault.from_list([FaultCode.NONE] * JOINT_COUNT)
        assert len(fault) == JOINT_COUNT

    def test_has_any_fault_false(self):
        fault = L6Fault.from_list([FaultCode.NONE] * JOINT_COUNT)
        assert fault.has_any_fault() is False

    def test_has_any_fault_true(self):
        codes = [FaultCode.NONE] * JOINT_COUNT
        codes[0] = FaultCode.PHASE_A_OVERCURRENT
        fault = L6Fault.from_list(codes)
        assert fault.has_any_fault() is True

    def test_getitem(self):
        codes = [FaultCode.NONE] * JOINT_COUNT
        codes[2] = FaultCode.OVERLOAD_1
        fault = L6Fault.from_list(codes)
        assert fault[2] == FaultCode.OVERLOAD_1


class TestFaultCode:
    """Validate L6 FaultCode enum methods."""

    def test_none_has_no_fault(self):
        assert FaultCode.NONE.has_fault() is False

    def test_single_fault_detected(self):
        assert FaultCode.PHASE_A_OVERCURRENT.has_fault() is True

    def test_combined_faults(self):
        combined = FaultCode.PHASE_A_OVERCURRENT | FaultCode.OVERLOAD_1
        assert combined.has_fault() is True

    def test_get_fault_names_none(self):
        assert FaultCode.NONE.get_fault_names() == ["No faults"]

    def test_get_fault_names_single(self):
        names = FaultCode.PHASE_A_OVERCURRENT.get_fault_names()
        assert "Phase A overcurrent" in names

    def test_get_fault_names_combined(self):
        combined = FaultCode.PHASE_A_OVERCURRENT | FaultCode.OVERLOAD_1
        names = combined.get_fault_names()
        assert "Phase A overcurrent" in names
        assert "Overload level 1" in names

    def test_all_fault_types(self):
        for code in [
            FaultCode.PHASE_B_OVERCURRENT,
            FaultCode.PHASE_C_OVERCURRENT,
            FaultCode.PHASE_A_OVERCURRENT,
            FaultCode.OVERLOAD_1,
            FaultCode.OVERLOAD_2,
            FaultCode.MOTOR_OVERTEMP,
            FaultCode.MCU_OVERTEMP,
        ]:
            assert code.has_fault() is True
            assert len(code.get_fault_names()) == 1
