"""Tests for O6 FaultManager with hardware."""

import time

import pytest

from linkerbot import O6
from linkerbot.hand.o6 import FaultCode, O6Fault

pytestmark = [pytest.mark.o6, pytest.mark.sensor]


class TestFaultManagerBlocking:
    """Test FaultManager blocking mode."""

    def test_get_blocking_returns_valid_data(self, o6_hand: O6):
        """Blocking read should return FaultData with 6 FaultCode values."""
        data = o6_hand.fault.get_blocking(timeout_ms=100)

        assert data is not None, "get_blocking should return FaultData"
        assert isinstance(data.faults, O6Fault), "faults should be an O6Fault instance"
        assert len(data.faults) == 6, "O6Fault should have exactly 6 joints"

        for i in range(6):
            assert isinstance(data.faults[i], FaultCode), (
                f"Joint {i} should be a FaultCode"
            )

    def test_no_fault_on_healthy_device(self, o6_hand: O6):
        """All 6 joints should report FaultCode.NONE on a healthy device."""
        data = o6_hand.fault.get_blocking(timeout_ms=100)

        assert data.faults.thumb_flex == FaultCode.NONE, (
            "thumb_flex should have no fault"
        )
        assert data.faults.thumb_abd == FaultCode.NONE, "thumb_abd should have no fault"
        assert data.faults.index == FaultCode.NONE, "index should have no fault"
        assert data.faults.middle == FaultCode.NONE, "middle should have no fault"
        assert data.faults.ring == FaultCode.NONE, "ring should have no fault"
        assert data.faults.pinky == FaultCode.NONE, "pinky should have no fault"

    def test_has_any_fault_returns_false_when_healthy(self, o6_hand: O6):
        """has_any_fault should return False on a healthy device."""
        data = o6_hand.fault.get_blocking(timeout_ms=100)

        assert data.faults.has_any_fault() is False, (
            "Healthy device should have no faults"
        )


class TestFaultManagerOperations:
    """Test FaultManager operations."""

    def test_fault_code_methods(self, o6_hand: O6):
        """FaultCode methods should be callable and return correct types."""
        data = o6_hand.fault.get_blocking(timeout_ms=100)

        for i, code in enumerate(data.faults.to_list()):
            result = code.has_fault()
            assert isinstance(result, bool), (
                f"Joint {i}: has_fault() should return bool"
            )

            names = code.get_fault_names()
            assert isinstance(names, list), (
                f"Joint {i}: get_fault_names() should return list"
            )
            assert all(isinstance(n, str) for n in names), (
                f"Joint {i}: get_fault_names() should return list of strings"
            )


class TestFaultManagerSnapshot:
    """Test FaultManager snapshot mode."""

    def test_snapshot_populated_after_read(self, o6_hand: O6):
        """get_snapshot should return non-None FaultData after a blocking read."""
        o6_hand.fault.get_blocking(timeout_ms=100)

        data = o6_hand.fault.get_snapshot()

        assert data is not None, "Snapshot should be populated after blocking read"
        assert isinstance(data.faults, O6Fault), "Snapshot faults should be O6Fault"
        assert len(data.faults) == 6, "Snapshot should have 6 joints"
        assert data.timestamp > 0, "Snapshot timestamp should be positive"
        assert data.timestamp <= time.time(), (
            "Snapshot timestamp should not be in the future"
        )
