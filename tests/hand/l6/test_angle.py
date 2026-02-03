"""Tests for L6 AngleManager with hardware."""

import time

import pytest

from linkerbot import L6
from linkerbot.hand.l6 import L6Angle

pytestmark = pytest.mark.l6


class TestAngleManagerBlocking:
    """Test AngleManager blocking mode."""

    def test_get_angles_blocking_returns_valid_data(self, l6_hand: L6):
        """Blocking read should return valid angle data."""
        data = l6_hand.angle.get_angles_blocking(timeout_ms=1000)

        assert data is not None
        assert len(data.angles) == 6
        for angle in data.angles.to_list():
            assert 0 <= angle <= 100

    def test_get_angles_blocking_has_timestamp(self, l6_hand: L6):
        """Angle data should have a valid timestamp."""
        data = l6_hand.angle.get_angles_blocking(timeout_ms=1000)

        assert data.timestamp > 0
        assert data.timestamp <= time.time()


class TestAngleManagerSetAngles:
    """Test AngleManager set_angles method."""

    def test_set_angles_with_list(self, l6_hand: L6):
        """set_angles should accept list of floats."""
        target = [50.0, 50.0, 50.0, 50.0, 50.0, 50.0]

        l6_hand.angle.set_angles(target)
        time.sleep(0.5)

        data = l6_hand.angle.get_angles_blocking(timeout_ms=500)
        assert data is not None

    def test_set_angles_with_l6angle(self, l6_hand: L6):
        """set_angles should accept L6Angle instance."""
        target = L6Angle(
            thumb_flex=50.0,
            thumb_abd=50.0,
            index=50.0,
            middle=50.0,
            ring=50.0,
            pinky=50.0,
        )

        l6_hand.angle.set_angles(target)
        time.sleep(0.5)

        data = l6_hand.angle.get_angles_blocking(timeout_ms=500)
        assert data is not None

    def test_set_and_read_angles_within_tolerance(self, l6_hand: L6):
        """Set angles and verify response is within tolerance."""
        target = [50.0, 50.0, 50.0, 50.0, 50.0, 50.0]

        l6_hand.angle.set_angles(target)
        time.sleep(0.5)

        data = l6_hand.angle.get_angles_blocking(timeout_ms=500)

        for i, expected in enumerate(target):
            assert abs(data.angles[i] - expected) < 15.0, (
                f"Angle {i} expected ~{expected}, got {data.angles[i]}"
            )


class TestAngleManagerStreaming:
    """Test AngleManager streaming mode."""

    def test_stream_produces_continuous_data(self, l6_hand: L6):
        """Streaming should produce continuous angle data."""
        received = []

        q = l6_hand.angle.stream(interval_ms=100)
        try:
            for data in q:
                received.append(data)
                if len(received) >= 10:
                    break
        finally:
            l6_hand.angle.stop_streaming()

        assert len(received) == 10
        for data in received:
            assert len(data.angles) == 6

    def test_stop_streaming_is_idempotent(self, l6_hand: L6):
        """stop_streaming() should be safe to call multiple times."""
        l6_hand.angle.stream(interval_ms=100)
        l6_hand.angle.stop_streaming()
        l6_hand.angle.stop_streaming()


class TestAngleManagerCache:
    """Test AngleManager cache mode."""

    def test_get_current_angles_after_request(self, l6_hand: L6):
        """get_current_angles should return cached data after a request."""
        l6_hand.angle.get_angles_blocking(timeout_ms=500)

        data = l6_hand.angle.get_current_angles()

        assert data is not None
        assert len(data.angles) == 6
