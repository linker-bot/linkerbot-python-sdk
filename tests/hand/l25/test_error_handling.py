"""Tests for L25 error handling with hardware."""

import pytest

from linkerbot import L25
from linkerbot.exceptions import ValidationError
from linkerbot.hand.l25 import SensorSource

pytestmark = [pytest.mark.l25, pytest.mark.error_handling]


class TestAngleErrorHandling:
    """Validate angle-related error handling."""

    def test_get_blocking_timeout_zero(self, l25_hand: L25):
        with pytest.raises(ValidationError):
            l25_hand.angle.get_blocking(timeout_ms=0)

    def test_get_blocking_timeout_negative(self, l25_hand: L25):
        with pytest.raises(ValidationError):
            l25_hand.angle.get_blocking(timeout_ms=-1)

    def test_set_angles_empty_list(self, l25_hand: L25):
        with pytest.raises(ValueError):
            l25_hand.angle.set_angles([])

    def test_set_angles_too_few(self, l25_hand: L25):
        with pytest.raises(ValueError):
            l25_hand.angle.set_angles([50.0] * 15)

    def test_set_angles_too_many(self, l25_hand: L25):
        with pytest.raises(ValueError):
            l25_hand.angle.set_angles([50.0] * 17)

    def test_set_angles_negative_value(self, l25_hand: L25):
        with pytest.raises(ValueError):
            l25_hand.angle.set_angles([-1.0] + [50.0] * 15)

    def test_set_angles_over_100(self, l25_hand: L25):
        with pytest.raises(ValueError):
            l25_hand.angle.set_angles([101.0] + [50.0] * 15)


class TestSpeedErrorHandling:
    """Validate speed-related error handling."""

    def test_get_blocking_timeout_zero(self, l25_hand: L25):
        with pytest.raises(ValidationError):
            l25_hand.speed.get_blocking(timeout_ms=0)

    def test_set_speeds_wrong_length(self, l25_hand: L25):
        with pytest.raises(ValueError):
            l25_hand.speed.set_speeds([50.0] * 15)


class TestTorqueErrorHandling:
    """Validate torque-related error handling."""

    def test_get_blocking_timeout_zero(self, l25_hand: L25):
        with pytest.raises(ValidationError):
            l25_hand.torque.get_blocking(timeout_ms=0)

    def test_set_torques_wrong_length(self, l25_hand: L25):
        with pytest.raises(ValueError):
            l25_hand.torque.set_torques([50.0] * 15)


class TestPollingErrorHandling:
    """Validate polling-related error handling."""

    def test_start_polling_interval_zero(self, l25_hand: L25):
        with pytest.raises(ValidationError):
            l25_hand.start_polling({SensorSource.ANGLE: 0})

    def test_start_polling_interval_negative(self, l25_hand: L25):
        with pytest.raises(ValidationError):
            l25_hand.start_polling({SensorSource.ANGLE: -0.1})
