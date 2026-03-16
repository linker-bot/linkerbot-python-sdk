"""Tests for L6 TemperatureManager with hardware."""

import time

import pytest

from linkerbot import L6

pytestmark = [pytest.mark.l6, pytest.mark.sensor]


class TestTemperatureManagerBlocking:
    """Test TemperatureManager blocking mode."""

    def test_get_blocking_returns_valid_data(self, l6_hand: L6):
        """Blocking read should return 6 temperature values in reasonable range."""
        data = l6_hand.temperature.get_blocking(timeout_ms=100)

        assert data is not None
        assert len(data.temperatures) == 6
        for temp in data.temperatures.to_list():
            assert 0 <= temp <= 100, (
                f"Temperature {temp}°C out of reasonable range (0-100)"
            )

    def test_get_blocking_has_timestamp(self, l6_hand: L6):
        """Temperature data should have a valid timestamp."""
        data = l6_hand.temperature.get_blocking(timeout_ms=100)

        assert data.timestamp > 0, "Timestamp should be positive"
        assert data.timestamp <= time.time(), "Timestamp should not be in the future"

    def test_temperature_field_access(self, l6_hand: L6):
        """Should be able to access temperature fields by name."""
        data = l6_hand.temperature.get_blocking(timeout_ms=100)

        assert isinstance(data.temperatures.thumb_flex, float), (
            "thumb_flex should be float"
        )
        assert isinstance(data.temperatures.thumb_abd, float), (
            "thumb_abd should be float"
        )
        assert isinstance(data.temperatures.index, float), "index should be float"
        assert isinstance(data.temperatures.middle, float), "middle should be float"
        assert isinstance(data.temperatures.ring, float), "ring should be float"
        assert isinstance(data.temperatures.pinky, float), "pinky should be float"


class TestTemperatureManagerSnapshot:
    """Test TemperatureManager snapshot mode."""

    def test_snapshot_populated_after_read(self, l6_hand: L6):
        """get_snapshot should return non-None after a blocking read."""
        l6_hand.temperature.get_blocking(timeout_ms=100)

        data = l6_hand.temperature.get_snapshot()

        assert data is not None, "Snapshot should be populated after blocking read"
        assert len(data.temperatures) == 6


class TestTemperatureExercise:
    """Test temperature after motion."""

    def test_temperature_after_exercise(self, l6_hand: L6):
        """Temperatures should be readable after exercising the hand."""
        baseline = l6_hand.temperature.get_blocking(timeout_ms=100)
        assert baseline is not None
        print(
            f"\n  Baseline temps: {[f'{t:.1f}' for t in baseline.temperatures.to_list()]}"
        )

        # Exercise: half grip 10 times
        for i in range(10):
            l6_hand.angle.set_angles([50.0] * 6)
            time.sleep(0.9)
            l6_hand.angle.set_angles([100.0] * 6)
            time.sleep(0.9)
            print(f"  Exercise cycle {i + 1}/10 complete")

        after = l6_hand.temperature.get_blocking(timeout_ms=100)
        assert after is not None
        print(f"  After exercise: {[f'{t:.1f}' for t in after.temperatures.to_list()]}")

        snapshot = l6_hand.temperature.get_snapshot()
        assert snapshot is not None, "Snapshot should be populated after blocking read"
        assert snapshot.timestamp >= after.timestamp, (
            "Snapshot timestamp should be no earlier than last blocking read"
        )
