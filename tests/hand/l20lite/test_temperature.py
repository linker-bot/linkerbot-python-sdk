"""Tests for L20Lite TemperatureManager with hardware."""

import time

import pytest

from linkerbot import L20lite

pytestmark = [pytest.mark.l20lite, pytest.mark.sensor]


class TestTemperatureManagerBlocking:
    """Test TemperatureManager blocking mode."""

    def test_get_blocking_returns_valid_data(self, l20lite_hand: L20lite):
        """Blocking read should return 10 temperature values in reasonable range."""
        data = l20lite_hand.temperature.get_blocking(timeout_ms=100)

        assert data is not None
        assert len(data.temperatures) == 10
        for temp in data.temperatures.to_list():
            assert 0 <= temp <= 100, (
                f"Temperature {temp} C out of reasonable range (0-100)"
            )

    def test_get_blocking_has_timestamp(self, l20lite_hand: L20lite):
        """Temperature data should have a valid timestamp."""
        data = l20lite_hand.temperature.get_blocking(timeout_ms=100)

        assert data.timestamp > 0, "Timestamp should be positive"
        assert data.timestamp <= time.time(), "Timestamp should not be in the future"

    def test_temperature_field_access(self, l20lite_hand: L20lite):
        """Should be able to access temperature fields by name."""
        data = l20lite_hand.temperature.get_blocking(timeout_ms=100)

        assert isinstance(data.temperatures.thumb_flex, float), (
            "thumb_flex should be float"
        )
        assert isinstance(data.temperatures.thumb_abd, float), (
            "thumb_abd should be float"
        )
        assert isinstance(data.temperatures.index_flex, float), (
            "index_flex should be float"
        )
        assert isinstance(data.temperatures.middle_flex, float), (
            "middle_flex should be float"
        )
        assert isinstance(data.temperatures.ring_flex, float), (
            "ring_flex should be float"
        )
        assert isinstance(data.temperatures.pinky_flex, float), (
            "pinky_flex should be float"
        )
        assert isinstance(data.temperatures.index_abd, float), (
            "index_abd should be float"
        )
        assert isinstance(data.temperatures.ring_abd, float), "ring_abd should be float"
        assert isinstance(data.temperatures.pinky_abd, float), (
            "pinky_abd should be float"
        )
        assert isinstance(data.temperatures.thumb_yaw, float), (
            "thumb_yaw should be float"
        )


class TestTemperatureManagerSnapshot:
    """Test TemperatureManager snapshot mode."""

    def test_snapshot_populated_after_read(self, l20lite_hand: L20lite):
        """get_snapshot should return non-None after a blocking read."""
        l20lite_hand.temperature.get_blocking(timeout_ms=100)

        data = l20lite_hand.temperature.get_snapshot()

        assert data is not None, "Snapshot should be populated after blocking read"
        assert len(data.temperatures) == 10
