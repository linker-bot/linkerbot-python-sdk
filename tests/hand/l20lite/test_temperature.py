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
        print(f"\n  Temperatures: {[f'{t:.1f}' for t in data.temperatures.to_list()]}")

    def test_get_blocking_has_timestamp(self, l20lite_hand: L20lite):
        """Temperature data should have a valid timestamp."""
        data = l20lite_hand.temperature.get_blocking(timeout_ms=100)

        assert data.timestamp > 0
        assert data.timestamp <= time.time()

    def test_temperature_field_access(self, l20lite_hand: L20lite):
        """Should be able to access temperature fields by name."""
        data = l20lite_hand.temperature.get_blocking(timeout_ms=100)

        for field in [
            "thumb_flex",
            "thumb_abd",
            "index_flex",
            "middle_flex",
            "ring_flex",
            "pinky_flex",
            "index_abd",
            "ring_abd",
            "pinky_abd",
            "thumb_yaw",
        ]:
            assert isinstance(getattr(data.temperatures, field), float), (
                f"{field} should be float"
            )


class TestTemperatureAfterExercise:
    """Test temperature change after exercising the hand."""

    def test_temperature_changes_after_exercise(self, l20lite_hand: L20lite):
        """After exercising the hand, temperature readings should update."""
        baseline = l20lite_hand.temperature.get_blocking(timeout_ms=100)
        print(
            f"\n  Baseline temps: {[f'{t:.1f}' for t in baseline.temperatures.to_list()]}"
        )

        # Exercise: half grip 10 times
        for i in range(10):
            l20lite_hand.angle.set_angles([50.0] * 6 + [100.0] * 4)
            time.sleep(1.5)
            l20lite_hand.angle.set_angles([100.0] * 10)
            time.sleep(1.5)
            print(f"  Exercise cycle {i + 1}/10 complete")

        after = l20lite_hand.temperature.get_blocking(timeout_ms=100)
        print(f"  After exercise: {[f'{t:.1f}' for t in after.temperatures.to_list()]}")

        snapshot = l20lite_hand.temperature.get_snapshot()
        assert snapshot is not None, "Snapshot should be populated after blocking read"
        assert snapshot.timestamp >= after.timestamp


class TestTemperatureManagerSnapshot:
    """Test TemperatureManager snapshot mode."""

    def test_snapshot_populated_after_read(self, l20lite_hand: L20lite):
        """get_snapshot should return non-None after a blocking read."""
        l20lite_hand.temperature.get_blocking(timeout_ms=100)

        data = l20lite_hand.temperature.get_snapshot()
        assert data is not None
        assert len(data.temperatures) == 10
