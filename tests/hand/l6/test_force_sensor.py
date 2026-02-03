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


class TestForceSensorManagerStreaming:
    """Test ForceSensorManager streaming mode."""

    def test_stream_returns_iterable_queue(self, l6_hand: L6):
        """stream() should return an iterable queue."""
        q = l6_hand.force_sensor.stream(interval_ms=100)
        try:
            assert hasattr(q, "__iter__")
            assert hasattr(q, "get")
        finally:
            l6_hand.force_sensor.stop_streaming()

    def test_stream_produces_all_fingers_data(self, l6_hand: L6):
        """Streaming should produce complete AllFingersData."""
        q = l6_hand.force_sensor.stream(interval_ms=100)
        try:
            data = q.get(timeout=3.0)

            assert hasattr(data, "thumb")
            assert hasattr(data, "index")
            assert hasattr(data, "middle")
            assert hasattr(data, "ring")
            assert hasattr(data, "pinky")
        finally:
            l6_hand.force_sensor.stop_streaming()

    def test_stream_produces_continuous_data(self, l6_hand: L6):
        """Streaming should produce continuous data."""
        received = []

        q = l6_hand.force_sensor.stream(interval_ms=100)
        try:
            for data in q:
                received.append(data)
                if len(received) >= 5:
                    break
        finally:
            l6_hand.force_sensor.stop_streaming()

        assert len(received) == 5

    def test_stop_streaming_is_idempotent(self, l6_hand: L6):
        """stop_streaming() should be safe to call multiple times."""
        l6_hand.force_sensor.stream(interval_ms=100)
        l6_hand.force_sensor.stop_streaming()
        l6_hand.force_sensor.stop_streaming()


class TestForceSensorManagerCache:
    """Test ForceSensorManager cache mode."""

    def test_get_latest_data_returns_dict(self, l6_hand: L6):
        """get_latest_data should return a dict with all finger names."""
        data = l6_hand.force_sensor.get_latest_data()

        assert isinstance(data, dict)
        assert "thumb" in data
        assert "index" in data
        assert "middle" in data
        assert "ring" in data
        assert "pinky" in data

    def test_get_latest_data_after_request(self, l6_hand: L6):
        """Cache should be populated after a blocking request."""
        l6_hand.force_sensor.get_data_blocking(timeout_ms=2000)

        data = l6_hand.force_sensor.get_latest_data()

        # At least some fingers should have data
        has_data = sum(1 for v in data.values() if v is not None)
        assert has_data > 0
