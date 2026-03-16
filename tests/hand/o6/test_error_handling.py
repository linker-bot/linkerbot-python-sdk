"""Tests for O6 error handling with hardware."""

import pytest

from linkerbot import O6
from linkerbot.exceptions import ValidationError
from linkerbot.hand.o6 import SensorSource

pytestmark = [pytest.mark.o6, pytest.mark.error_handling]


class TestAngleErrorHandling:
    """Validate angle-related error handling."""

    def test_get_blocking_timeout_zero(self, o6_hand: O6):
        with pytest.raises(ValidationError):
            o6_hand.angle.get_blocking(timeout_ms=0)

    def test_get_blocking_timeout_negative(self, o6_hand: O6):
        with pytest.raises(ValidationError):
            o6_hand.angle.get_blocking(timeout_ms=-1)

    def test_set_angles_empty_list(self, o6_hand: O6):
        with pytest.raises(ValueError):
            o6_hand.angle.set_angles([])

    def test_set_angles_too_few(self, o6_hand: O6):
        with pytest.raises(ValueError):
            o6_hand.angle.set_angles([50.0] * 5)

    def test_set_angles_too_many(self, o6_hand: O6):
        with pytest.raises(ValueError):
            o6_hand.angle.set_angles([50.0] * 7)

    def test_set_angles_negative_value(self, o6_hand: O6):
        with pytest.raises(ValueError):
            o6_hand.angle.set_angles([-1.0] + [50.0] * 5)

    def test_set_angles_over_100(self, o6_hand: O6):
        with pytest.raises(ValueError):
            o6_hand.angle.set_angles([101.0] + [50.0] * 5)


class TestSpeedErrorHandling:
    """Validate speed-related error handling.

    O6 speed supports get_blocking (unlike L6 which is write-only).
    """

    def test_get_blocking_timeout_zero(self, o6_hand: O6):
        with pytest.raises(ValidationError):
            o6_hand.speed.get_blocking(timeout_ms=0)

    def test_set_speeds_wrong_length(self, o6_hand: O6):
        with pytest.raises(ValueError):
            o6_hand.speed.set_speeds([50.0] * 5)


class TestTorqueErrorHandling:
    """Validate torque-related error handling."""

    def test_get_blocking_timeout_zero(self, o6_hand: O6):
        with pytest.raises(ValidationError):
            o6_hand.torque.get_blocking(timeout_ms=0)

    def test_set_torques_wrong_length(self, o6_hand: O6):
        with pytest.raises(ValueError):
            o6_hand.torque.set_torques([50.0] * 5)


class TestAccelerationErrorHandling:
    """Validate acceleration-related error handling (O6-specific)."""

    def test_get_blocking_timeout_zero(self, o6_hand: O6):
        with pytest.raises(ValidationError):
            o6_hand.acceleration.get_blocking(timeout_ms=0)

    def test_set_accelerations_wrong_length(self, o6_hand: O6):
        with pytest.raises(ValidationError):
            o6_hand.acceleration.set_accelerations([50.0] * 5)


class TestPollingErrorHandling:
    """Validate polling-related error handling."""

    def test_start_polling_interval_zero(self, o6_hand: O6):
        with pytest.raises(ValidationError):
            o6_hand.start_polling({SensorSource.ANGLE: 0})

    def test_start_polling_interval_negative(self, o6_hand: O6):
        with pytest.raises(ValidationError):
            o6_hand.start_polling({SensorSource.ANGLE: -0.1})
