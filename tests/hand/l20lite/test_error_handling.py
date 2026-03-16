"""Tests for L20Lite error handling with hardware."""

import pytest

from linkerbot import L20lite
from linkerbot.exceptions import ValidationError
from linkerbot.hand.l20lite import SensorSource

pytestmark = [pytest.mark.l20lite, pytest.mark.error_handling]


class TestAngleErrorHandling:
    """Validate angle-related error handling."""

    def test_get_blocking_timeout_zero(self, l20lite_hand: L20lite):
        with pytest.raises(ValidationError):
            l20lite_hand.angle.get_blocking(timeout_ms=0)

    def test_get_blocking_timeout_negative(self, l20lite_hand: L20lite):
        with pytest.raises(ValidationError):
            l20lite_hand.angle.get_blocking(timeout_ms=-1)

    def test_set_angles_empty_list(self, l20lite_hand: L20lite):
        with pytest.raises(ValueError):
            l20lite_hand.angle.set_angles([])

    def test_set_angles_too_few(self, l20lite_hand: L20lite):
        with pytest.raises(ValueError):
            l20lite_hand.angle.set_angles([50.0] * 9)

    def test_set_angles_too_many(self, l20lite_hand: L20lite):
        with pytest.raises(ValueError):
            l20lite_hand.angle.set_angles([50.0] * 11)

    def test_set_angles_negative_value(self, l20lite_hand: L20lite):
        with pytest.raises(ValueError):
            l20lite_hand.angle.set_angles([-1.0] + [50.0] * 9)

    def test_set_angles_over_100(self, l20lite_hand: L20lite):
        with pytest.raises(ValueError):
            l20lite_hand.angle.set_angles([101.0] + [50.0] * 9)


class TestSpeedErrorHandling:
    """Validate speed-related error handling."""

    def test_get_blocking_timeout_zero(self, l20lite_hand: L20lite):
        with pytest.raises(ValidationError):
            l20lite_hand.speed.get_blocking(timeout_ms=0)

    def test_set_speeds_wrong_length(self, l20lite_hand: L20lite):
        with pytest.raises(ValueError):
            l20lite_hand.speed.set_speeds([50.0] * 9)


class TestTorqueErrorHandling:
    """Validate torque-related error handling."""

    def test_get_blocking_timeout_zero(self, l20lite_hand: L20lite):
        with pytest.raises(ValidationError):
            l20lite_hand.torque.get_blocking(timeout_ms=0)

    def test_set_torques_wrong_length(self, l20lite_hand: L20lite):
        with pytest.raises(ValueError):
            l20lite_hand.torque.set_torques([50.0] * 9)


class TestPollingErrorHandling:
    """Validate polling-related error handling."""

    def test_start_polling_interval_zero(self, l20lite_hand: L20lite):
        with pytest.raises(ValidationError):
            l20lite_hand.start_polling({SensorSource.ANGLE: 0})

    def test_start_polling_interval_negative(self, l20lite_hand: L20lite):
        with pytest.raises(ValidationError):
            l20lite_hand.start_polling({SensorSource.ANGLE: -0.1})
