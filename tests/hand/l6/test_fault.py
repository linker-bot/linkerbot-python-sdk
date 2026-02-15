"""Tests for L6 FaultManager with hardware."""

import time

import pytest

from linkerbot import L6
from linkerbot.hand.l6 import FaultCode, L6Fault

pytestmark = [pytest.mark.l6, pytest.mark.sensor]


class TestFaultManagerBlocking:
    """Test FaultManager blocking mode."""

    def test_get_blocking_returns_valid_data(self, l6_hand: L6):
        """Blocking read should return FaultData with 6 FaultCode values."""
        data = l6_hand.fault.get_blocking(timeout_ms=100)

        assert data is not None, "get_blocking should return FaultData"
        assert isinstance(data.faults, L6Fault), "faults should be an L6Fault instance"
        assert len(data.faults) == 6, "L6Fault should have exactly 6 joints"

        for i in range(6):
            assert isinstance(data.faults[i], FaultCode), (
                f"Joint {i} should be a FaultCode"
            )

    def test_no_fault_on_healthy_device(self, l6_hand: L6):
        """All 6 joints should report FaultCode.NONE on a healthy device."""
        data = l6_hand.fault.get_blocking(timeout_ms=100)

        assert data.faults.thumb_flex == FaultCode.NONE, (
            "thumb_flex should have no fault"
        )
        assert data.faults.thumb_abd == FaultCode.NONE, "thumb_abd should have no fault"
        assert data.faults.index == FaultCode.NONE, "index should have no fault"
        assert data.faults.middle == FaultCode.NONE, "middle should have no fault"
        assert data.faults.ring == FaultCode.NONE, "ring should have no fault"
        assert data.faults.pinky == FaultCode.NONE, "pinky should have no fault"

    def test_has_any_fault_returns_false_when_healthy(self, l6_hand: L6):
        """has_any_fault should return False on a healthy device."""
        data = l6_hand.fault.get_blocking(timeout_ms=100)

        assert data.faults.has_any_fault() is False, (
            "Healthy device should have no faults"
        )


class TestFaultManagerOperations:
    """Test FaultManager operations."""

    def test_clear_faults_no_error(self, l6_hand: L6):
        """clear_faults should execute without raising an exception."""
        l6_hand.fault.clear_faults()

    def test_fault_code_methods(self, l6_hand: L6):
        """FaultCode methods should be callable and return correct types."""
        data = l6_hand.fault.get_blocking(timeout_ms=100)

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

    def test_snapshot_populated_after_read(self, l6_hand: L6):
        """get_snapshot should return non-None FaultData after a blocking read."""
        l6_hand.fault.get_blocking(timeout_ms=100)

        data = l6_hand.fault.get_snapshot()

        assert data is not None, "Snapshot should be populated after blocking read"
        assert isinstance(data.faults, L6Fault), "Snapshot faults should be L6Fault"
        assert len(data.faults) == 6, "Snapshot should have 6 joints"
        assert data.timestamp > 0, "Snapshot timestamp should be positive"
        assert data.timestamp <= time.time(), (
            "Snapshot timestamp should not be in the future"
        )
