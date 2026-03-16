"""Unit tests for L20Lite data classes (no hardware required)."""

import pytest

from linkerbot.hand.l20lite import (
    FaultCode,
    L20liteAngle,
    L20liteFault,
    L20liteSpeed,
    L20liteTorque,
)

pytestmark = [pytest.mark.l20lite, pytest.mark.validation]

JOINT_COUNT = 10
VALID_VALUES = [50.0] * JOINT_COUNT


class TestL20liteAngle:
    """Validate L20liteAngle construction, boundary, and round-trip."""

    def test_from_list_wrong_length_short(self):
        with pytest.raises(ValueError, match="Expected 10"):
            L20liteAngle.from_list([50.0] * 9)

    def test_from_list_wrong_length_long(self):
        with pytest.raises(ValueError, match="Expected 10"):
            L20liteAngle.from_list([50.0] * 11)

    def test_from_list_negative_value(self):
        with pytest.raises(ValueError, match="out of range"):
            L20liteAngle.from_list([-1.0] + [50.0] * 9)

    def test_from_list_over_100(self):
        with pytest.raises(ValueError, match="out of range"):
            L20liteAngle.from_list([101.0] + [50.0] * 9)

    def test_from_list_non_numeric(self):
        with pytest.raises(ValueError, match="must be float/int"):
            L20liteAngle.from_list(["a"] + [50.0] * 9)

    def test_round_trip(self):
        angle = L20liteAngle.from_list(VALID_VALUES)
        assert angle.to_list() == VALID_VALUES

    def test_getitem(self):
        angle = L20liteAngle.from_list(VALID_VALUES)
        for i in range(JOINT_COUNT):
            assert angle[i] == VALID_VALUES[i]

    def test_len(self):
        angle = L20liteAngle.from_list(VALID_VALUES)
        assert len(angle) == JOINT_COUNT

    def test_getitem_out_of_range(self):
        angle = L20liteAngle.from_list(VALID_VALUES)
        with pytest.raises(IndexError):
            _ = angle[JOINT_COUNT]

    def test_boundary_zero(self):
        angle = L20liteAngle.from_list([0.0] * JOINT_COUNT)
        assert angle.to_list() == [0.0] * JOINT_COUNT

    def test_boundary_one_hundred(self):
        angle = L20liteAngle.from_list([100.0] * JOINT_COUNT)
        assert angle.to_list() == [100.0] * JOINT_COUNT


class TestL20liteSpeed:
    """Validate L20liteSpeed construction and boundary."""

    def test_from_list_wrong_length(self):
        with pytest.raises(ValueError, match="Expected 10"):
            L20liteSpeed.from_list([50.0] * 9)

    def test_from_list_negative_value(self):
        with pytest.raises(ValueError, match="out of range"):
            L20liteSpeed.from_list([-1.0] + [50.0] * 9)

    def test_from_list_over_100(self):
        with pytest.raises(ValueError, match="out of range"):
            L20liteSpeed.from_list([101.0] + [50.0] * 9)

    def test_from_list_non_numeric(self):
        with pytest.raises(ValueError, match="must be float/int"):
            L20liteSpeed.from_list(["a"] + [50.0] * 9)

    def test_round_trip(self):
        speed = L20liteSpeed.from_list(VALID_VALUES)
        assert speed.to_list() == VALID_VALUES

    def test_len(self):
        assert len(L20liteSpeed.from_list(VALID_VALUES)) == JOINT_COUNT


class TestL20liteTorque:
    """Validate L20liteTorque construction and boundary."""

    def test_from_list_wrong_length(self):
        with pytest.raises(ValueError, match="Expected 10"):
            L20liteTorque.from_list([50.0] * 9)

    def test_from_list_negative_value(self):
        with pytest.raises(ValueError, match="out of range"):
            L20liteTorque.from_list([-1.0] + [50.0] * 9)

    def test_from_list_over_100(self):
        with pytest.raises(ValueError, match="out of range"):
            L20liteTorque.from_list([101.0] + [50.0] * 9)

    def test_from_list_non_numeric(self):
        with pytest.raises(ValueError, match="must be float/int"):
            L20liteTorque.from_list(["a"] + [50.0] * 9)

    def test_round_trip(self):
        torque = L20liteTorque.from_list(VALID_VALUES)
        assert torque.to_list() == VALID_VALUES

    def test_len(self):
        assert len(L20liteTorque.from_list(VALID_VALUES)) == JOINT_COUNT


class TestL20liteFault:
    """Validate L20liteFault construction and FaultCode operations."""

    def test_from_list_wrong_length(self):
        with pytest.raises(ValueError, match="Expected 10"):
            L20liteFault.from_list([FaultCode.NONE] * 9)

    def test_round_trip(self):
        codes = [FaultCode.NONE] * JOINT_COUNT
        fault = L20liteFault.from_list(codes)
        assert fault.to_list() == codes

    def test_len(self):
        fault = L20liteFault.from_list([FaultCode.NONE] * JOINT_COUNT)
        assert len(fault) == JOINT_COUNT

    def test_has_any_fault_false(self):
        fault = L20liteFault.from_list([FaultCode.NONE] * JOINT_COUNT)
        assert fault.has_any_fault() is False

    def test_has_any_fault_true(self):
        codes = [FaultCode.NONE] * JOINT_COUNT
        codes[0] = FaultCode.OVERCURRENT
        fault = L20liteFault.from_list(codes)
        assert fault.has_any_fault() is True

    def test_getitem(self):
        codes = [FaultCode.NONE] * JOINT_COUNT
        codes[2] = FaultCode.OVERTEMPERATURE
        fault = L20liteFault.from_list(codes)
        assert fault[2] == FaultCode.OVERTEMPERATURE


class TestFaultCode:
    """Validate FaultCode enum methods."""

    def test_none_has_no_fault(self):
        assert FaultCode.NONE.has_fault() is False

    def test_single_fault_detected(self):
        assert FaultCode.OVERCURRENT.has_fault() is True

    def test_combined_faults(self):
        combined = FaultCode.OVERCURRENT | FaultCode.OVERLOAD
        assert combined.has_fault() is True

    def test_get_fault_names_none(self):
        assert FaultCode.NONE.get_fault_names() == ["No faults"]

    def test_get_fault_names_single(self):
        names = FaultCode.OVERCURRENT.get_fault_names()
        assert "Overcurrent" in names

    def test_get_fault_names_combined(self):
        combined = FaultCode.OVERCURRENT | FaultCode.OVERLOAD
        names = combined.get_fault_names()
        assert "Overcurrent" in names
        assert "Overload" in names

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
