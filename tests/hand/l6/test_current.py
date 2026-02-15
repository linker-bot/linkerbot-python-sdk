"""Tests for L6 CurrentManager with hardware."""

import time

import pytest

from linkerbot import L6

pytestmark = [pytest.mark.l6, pytest.mark.sensor]


class TestCurrentManagerBlocking:
    """Test CurrentManager blocking mode."""

    def test_get_blocking_returns_valid_data(self, l6_hand: L6):
        """Blocking read should return 6 current values, all non-negative."""
        data = l6_hand.current.get_blocking(timeout_ms=100)

        assert data is not None
        assert len(data.currents) == 6
        for current in data.currents.to_list():
            assert current >= 0, f"Current {current} mA should be non-negative"

    def test_get_blocking_has_timestamp(self, l6_hand: L6):
        """Current data should have a valid timestamp."""
        data = l6_hand.current.get_blocking(timeout_ms=100)

        assert data.timestamp > 0, "Timestamp should be positive"
        assert data.timestamp <= time.time(), "Timestamp should not be in the future"

    def test_current_field_access(self, l6_hand: L6):
        """Should be able to access current fields by name."""
        data = l6_hand.current.get_blocking(timeout_ms=100)

        assert isinstance(data.currents.thumb_flex, float), "thumb_flex should be float"
        assert isinstance(data.currents.thumb_abd, float), "thumb_abd should be float"
        assert isinstance(data.currents.index, float), "index should be float"
        assert isinstance(data.currents.middle, float), "middle should be float"
        assert isinstance(data.currents.ring, float), "ring should be float"
        assert isinstance(data.currents.pinky, float), "pinky should be float"


class TestCurrentManagerSnapshot:
    """Test CurrentManager snapshot mode."""

    def test_snapshot_populated_after_read(self, l6_hand: L6):
        """get_snapshot should return non-None after a blocking read."""
        l6_hand.current.get_blocking(timeout_ms=100)

        data = l6_hand.current.get_snapshot()

        assert data is not None, "Snapshot should be populated after blocking read"
        assert len(data.currents) == 6
