"""Tests for L25 FaultManager with hardware."""

import time

import pytest

from linkerbot import L25
from linkerbot.hand.l25 import L25Fault, L25FaultCode

pytestmark = [pytest.mark.l25, pytest.mark.sensor]


class TestFaultManagerBlocking:
    """Test FaultManager blocking mode."""

    def test_get_blocking_returns_valid_data(self, l25_hand: L25):
        """Blocking read should return FaultData with 16 L25FaultCode values."""
        data = l25_hand.fault.get_blocking(timeout_ms=100)

        assert data is not None, "get_blocking should return FaultData"
        assert isinstance(data.faults, L25Fault), (
            "faults should be an L25Fault instance"
        )
        assert len(data.faults) == 16, "L25Fault should have exactly 16 joints"

        for i in range(16):
            assert isinstance(data.faults[i], L25FaultCode), (
                f"Joint {i} should be a L25FaultCode"
            )

        print(f"\n  Faults: {[str(f) for f in data.faults.to_list()]}")

    def test_no_fault_on_healthy_device(self, l25_hand: L25):
        """All 16 joints should report L25FaultCode.NONE on a healthy device."""
        data = l25_hand.fault.get_blocking(timeout_ms=100)

        for i in range(16):
            assert data.faults[i] == L25FaultCode.NONE, (
                f"Joint {i} should have no fault, got {data.faults[i]}"
            )

    def test_has_any_fault_returns_false_when_healthy(self, l25_hand: L25):
        """has_any_fault should return False on a healthy device."""
        data = l25_hand.fault.get_blocking(timeout_ms=100)

        assert data.faults.has_any_fault() is False, (
            "Healthy device should have no faults"
        )


class TestFaultManagerOperations:
    """Test FaultManager operations."""

    def test_fault_code_methods(self, l25_hand: L25):
        """L25FaultCode methods should be callable and return correct types."""
        data = l25_hand.fault.get_blocking(timeout_ms=100)

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

    def test_snapshot_populated_after_read(self, l25_hand: L25):
        """get_snapshot should return non-None FaultData after a blocking read."""
        l25_hand.fault.get_blocking(timeout_ms=100)

        data = l25_hand.fault.get_snapshot()

        assert data is not None, "Snapshot should be populated after blocking read"
        assert isinstance(data.faults, L25Fault), "Snapshot faults should be L25Fault"
        assert len(data.faults) == 16, "Snapshot should have 16 joints"
        assert data.timestamp > 0, "Snapshot timestamp should be positive"
        assert data.timestamp <= time.time(), (
            "Snapshot timestamp should not be in the future"
        )
