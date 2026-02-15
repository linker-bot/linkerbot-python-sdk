"""Tests for L25 TemperatureManager with hardware."""

import time

import pytest

from linkerbot import L25

pytestmark = [pytest.mark.l25, pytest.mark.sensor]


class TestTemperatureManagerBlocking:
    """Test TemperatureManager blocking mode."""

    def test_get_blocking_returns_valid_data(self, l25_hand: L25):
        """Blocking read should return 16 temperature values in reasonable range."""
        data = l25_hand.temperature.get_blocking(timeout_ms=100)

        assert data is not None
        assert len(data.temperatures) == 16
        for temp in data.temperatures.to_list():
            assert 0 <= temp <= 100, (
                f"Temperature {temp} C out of reasonable range (0-100)"
            )

    def test_get_blocking_has_timestamp(self, l25_hand: L25):
        """Temperature data should have a valid timestamp."""
        data = l25_hand.temperature.get_blocking(timeout_ms=100)

        assert data.timestamp > 0, "Timestamp should be positive"
        assert data.timestamp <= time.time(), "Timestamp should not be in the future"

    def test_temperature_field_access(self, l25_hand: L25):
        """Should be able to access temperature fields by name."""
        data = l25_hand.temperature.get_blocking(timeout_ms=100)

        assert isinstance(data.temperatures.thumb_abd, float), (
            "thumb_abd should be float"
        )
        assert isinstance(data.temperatures.thumb_yaw, float), (
            "thumb_yaw should be float"
        )
        assert isinstance(data.temperatures.thumb_root1, float), (
            "thumb_root1 should be float"
        )
        assert isinstance(data.temperatures.thumb_tip, float), (
            "thumb_tip should be float"
        )
        assert isinstance(data.temperatures.index_abd, float), (
            "index_abd should be float"
        )
        assert isinstance(data.temperatures.index_root1, float), (
            "index_root1 should be float"
        )
        assert isinstance(data.temperatures.index_tip, float), (
            "index_tip should be float"
        )
        assert isinstance(data.temperatures.middle_abd, float), (
            "middle_abd should be float"
        )
        assert isinstance(data.temperatures.middle_root1, float), (
            "middle_root1 should be float"
        )
        assert isinstance(data.temperatures.middle_tip, float), (
            "middle_tip should be float"
        )
        assert isinstance(data.temperatures.ring_abd, float), "ring_abd should be float"
        assert isinstance(data.temperatures.ring_root1, float), (
            "ring_root1 should be float"
        )
        assert isinstance(data.temperatures.ring_tip, float), "ring_tip should be float"
        assert isinstance(data.temperatures.pinky_abd, float), (
            "pinky_abd should be float"
        )
        assert isinstance(data.temperatures.pinky_root1, float), (
            "pinky_root1 should be float"
        )
        assert isinstance(data.temperatures.pinky_tip, float), (
            "pinky_tip should be float"
        )


class TestTemperatureManagerSnapshot:
    """Test TemperatureManager snapshot mode."""

    def test_snapshot_populated_after_read(self, l25_hand: L25):
        """get_snapshot should return non-None after a blocking read."""
        l25_hand.temperature.get_blocking(timeout_ms=100)

        data = l25_hand.temperature.get_snapshot()

        assert data is not None, "Snapshot should be populated after blocking read"
        assert len(data.temperatures) == 16
