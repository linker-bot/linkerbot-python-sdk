"""Tests for L20Lite FaultManager with hardware."""

import time

import pytest

from linkerbot import L20lite
from linkerbot.hand.l20lite import FaultCode, L20liteFault

pytestmark = [pytest.mark.l20lite, pytest.mark.sensor]


class TestFaultManagerBlocking:
    """Test FaultManager blocking mode."""

    def test_get_blocking_returns_valid_data(self, l20lite_hand: L20lite):
        """Blocking read should return FaultData with 10 FaultCode values."""
        data = l20lite_hand.fault.get_blocking(timeout_ms=100)

        assert data is not None, "get_blocking should return FaultData"
        assert isinstance(data.faults, L20liteFault), (
            "faults should be an L20liteFault instance"
        )
        assert len(data.faults) == 10, "L20liteFault should have exactly 10 joints"

        for i in range(10):
            assert isinstance(data.faults[i], FaultCode), (
                f"Joint {i} should be a FaultCode"
            )

        print(f"\n  Fault data: {[code.name for code in data.faults.to_list()]}")

    def test_no_fault_on_healthy_device(self, l20lite_hand: L20lite):
        """All 10 joints should report FaultCode.NONE on a healthy device."""
        data = l20lite_hand.fault.get_blocking(timeout_ms=100)

        assert data.faults.thumb_flex == FaultCode.NONE, (
            "thumb_flex should have no fault"
        )
        assert data.faults.thumb_abd == FaultCode.NONE, "thumb_abd should have no fault"
        assert data.faults.index_flex == FaultCode.NONE, (
            "index_flex should have no fault"
        )
        assert data.faults.middle_flex == FaultCode.NONE, (
            "middle_flex should have no fault"
        )
        assert data.faults.ring_flex == FaultCode.NONE, "ring_flex should have no fault"
        assert data.faults.pinky_flex == FaultCode.NONE, (
            "pinky_flex should have no fault"
        )
        assert data.faults.index_abd == FaultCode.NONE, "index_abd should have no fault"
        assert data.faults.ring_abd == FaultCode.NONE, "ring_abd should have no fault"
        assert data.faults.pinky_abd == FaultCode.NONE, "pinky_abd should have no fault"
        assert data.faults.thumb_yaw == FaultCode.NONE, "thumb_yaw should have no fault"

        print("\n  All joints report FaultCode.NONE - device healthy")

    def test_has_any_fault_returns_false_when_healthy(self, l20lite_hand: L20lite):
        """has_any_fault should return False on a healthy device."""
        data = l20lite_hand.fault.get_blocking(timeout_ms=100)

        assert data.faults.has_any_fault() is False, (
            "Healthy device should have no faults"
        )


class TestFaultManagerOperations:
    """Test FaultManager operations."""

    def test_fault_code_methods(self, l20lite_hand: L20lite):
        """FaultCode methods should be callable and return correct types."""
        data = l20lite_hand.fault.get_blocking(timeout_ms=100)

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

    def test_snapshot_populated_after_read(self, l20lite_hand: L20lite):
        """get_snapshot should return non-None FaultData after a blocking read."""
        l20lite_hand.fault.get_blocking(timeout_ms=100)

        data = l20lite_hand.fault.get_snapshot()

        assert data is not None, "Snapshot should be populated after blocking read"
        assert isinstance(data.faults, L20liteFault), (
            "Snapshot faults should be L20liteFault"
        )
        assert len(data.faults) == 10, "Snapshot should have 10 joints"
        assert data.timestamp > 0, "Snapshot timestamp should be positive"
        assert data.timestamp <= time.time(), (
            "Snapshot timestamp should not be in the future"
        )
