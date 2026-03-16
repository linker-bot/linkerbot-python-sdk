"""Tests for L25 TemperatureManager with hardware."""

import time

import pytest

from linkerbot import L25
from linkerbot.hand.l25 import SensorSource

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

        print(f"\n  Temperatures: {[f'{t:.1f}' for t in data.temperatures.to_list()]}")

    def test_get_blocking_has_timestamp(self, l25_hand: L25):
        """Temperature data should have a valid timestamp."""
        data = l25_hand.temperature.get_blocking(timeout_ms=100)

        assert data.timestamp > 0, "Timestamp should be positive"
        assert data.timestamp <= time.time(), "Timestamp should not be in the future"

    def test_temperature_field_access(self, l25_hand: L25):
        """Should be able to access all 16 temperature fields by name."""
        data = l25_hand.temperature.get_blocking(timeout_ms=100)
        temps = data.temperatures

        joint_names = [
            "thumb_abd",
            "thumb_yaw",
            "thumb_root1",
            "thumb_tip",
            "index_abd",
            "index_root1",
            "index_tip",
            "middle_abd",
            "middle_root1",
            "middle_tip",
            "ring_abd",
            "ring_root1",
            "ring_tip",
            "pinky_abd",
            "pinky_root1",
            "pinky_tip",
        ]
        for name in joint_names:
            assert isinstance(getattr(temps, name), float), f"{name} should be float"


class TestTemperatureManagerSnapshot:
    """Test TemperatureManager snapshot mode."""

    def test_snapshot_populated_after_read(self, l25_hand: L25):
        """get_snapshot should return non-None after a blocking read."""
        l25_hand.temperature.get_blocking(timeout_ms=100)

        data = l25_hand.temperature.get_snapshot()

        assert data is not None, "Snapshot should be populated after blocking read"
        assert len(data.temperatures) == 16


class TestTemperatureExercise:
    """Test temperature after motion."""

    def test_temperature_after_exercise(self, l25_hand: L25):
        """Temperatures should be readable after exercising the hand."""
        # Read baseline
        baseline = l25_hand.temperature.get_blocking(timeout_ms=100)
        assert baseline is not None
        baseline_list = baseline.temperatures.to_list()
        print(f"\n  Baseline temps: {[f'{t:.1f}' for t in baseline_list]}")

        # Exercise: open/close polling
        l25_hand.start_polling({SensorSource.TEMPERATURE: 0.1})
        time.sleep(1.0)
        l25_hand.stop_polling()

        # Read after exercise
        after = l25_hand.temperature.get_blocking(timeout_ms=100)
        assert after is not None
        after_list = after.temperatures.to_list()
        print(f"  After exercise: {[f'{t:.1f}' for t in after_list]}")

        # Timestamps should be different
        assert after.timestamp > baseline.timestamp, (
            "Second read should have a later timestamp"
        )
