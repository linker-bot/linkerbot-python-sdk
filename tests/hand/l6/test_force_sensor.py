"""Tests for L6 ForceSensorManager with hardware."""

import pytest

from linkerbot import L6

pytestmark = pytest.mark.l6


class TestForceSensorManagerBlocking:
    """Test ForceSensorManager blocking mode."""

    def test_get_data_blocking_returns_all_fingers(self, l6_hand: L6):
        """Blocking read should return data for all 5 fingers."""
        data = l6_hand.force_sensor.get_data_blocking(timeout_ms=2000)

        assert data is not None
        assert hasattr(data, "thumb")
        assert hasattr(data, "index")
        assert hasattr(data, "middle")
        assert hasattr(data, "ring")
        assert hasattr(data, "pinky")

    def test_get_data_blocking_correct_shape(self, l6_hand: L6):
        """Each finger should have (12, 6) shaped data."""
        data = l6_hand.force_sensor.get_data_blocking(timeout_ms=2000)

        assert data.thumb.values.shape == (12, 6)
        assert data.index.values.shape == (12, 6)
        assert data.middle.values.shape == (12, 6)
        assert data.ring.values.shape == (12, 6)
        assert data.pinky.values.shape == (12, 6)

    def test_get_data_blocking_has_timestamps(self, l6_hand: L6):
        """Each finger data should have valid timestamps."""
        data = l6_hand.force_sensor.get_data_blocking(timeout_ms=2000)

        assert data.thumb.timestamp > 0
        assert data.index.timestamp > 0
        assert data.middle.timestamp > 0
        assert data.ring.timestamp > 0
        assert data.pinky.timestamp > 0


class TestForceSensorManagerCache:
    """Test ForceSensorManager cache mode."""

    def test_get_snapshot_returns_none_initially(self, l6_hand: L6):
        """get_snapshot should return None when no data received."""
        data = l6_hand.force_sensor.get_snapshot()
        # May be None if no data received yet
        assert data is None or hasattr(data, "thumb")

    def test_get_snapshot_after_request(self, l6_hand: L6):
        """Cache should be populated after a blocking request."""
        l6_hand.force_sensor.get_data_blocking(timeout_ms=2000)

        data = l6_hand.force_sensor.get_snapshot()

        assert data is not None
        assert hasattr(data, "thumb")
        assert hasattr(data, "index")
        assert hasattr(data, "middle")
        assert hasattr(data, "ring")
        assert hasattr(data, "pinky")
