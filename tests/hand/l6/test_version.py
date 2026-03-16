"""Tests for L6 VersionManager with hardware."""

import time

import pytest

from linkerbot import L6
from linkerbot.hand.l6 import DeviceInfo, Version

pytestmark = [pytest.mark.l6, pytest.mark.lifecycle]


class TestDeviceInfo:
    """Test reading device information from real hardware."""

    def test_get_device_info_returns_complete(self, l6_hand: L6):
        """get_device_info should return a DeviceInfo with all fields populated."""
        info = l6_hand.version.get_device_info()

        assert isinstance(info, DeviceInfo), "Expected a DeviceInfo instance"
        assert info.serial_number is not None, "serial_number should not be None"
        assert info.pcb_version is not None, "pcb_version should not be None"
        assert info.firmware_version is not None, "firmware_version should not be None"
        assert info.mechanical_version is not None, (
            "mechanical_version should not be None"
        )

    def test_serial_number_format(self, l6_hand: L6):
        """serial_number should be a non-empty string of reasonable length."""
        info = l6_hand.version.get_device_info()

        assert isinstance(info.serial_number, str), "serial_number should be a string"
        assert len(info.serial_number) > 0, "serial_number should not be empty"
        assert len(info.serial_number) < 100, (
            "serial_number should be less than 100 chars"
        )

    def test_version_format(self, l6_hand: L6):
        """pcb, firmware, and mechanical versions should have non-negative integer fields."""
        info = l6_hand.version.get_device_info()

        for label, version in [
            ("pcb_version", info.pcb_version),
            ("firmware_version", info.firmware_version),
            ("mechanical_version", info.mechanical_version),
        ]:
            assert isinstance(version, Version), f"{label} should be a Version instance"
            assert isinstance(version.major, int), f"{label}.major should be an int"
            assert isinstance(version.minor, int), f"{label}.minor should be an int"
            assert isinstance(version.patch, int), f"{label}.patch should be an int"
            assert version.major >= 0, f"{label}.major should be non-negative"
            assert version.minor >= 0, f"{label}.minor should be non-negative"
            assert version.patch >= 0, f"{label}.patch should be non-negative"

    def test_device_info_has_timestamp(self, l6_hand: L6):
        """timestamp should be a positive value no later than now."""
        info = l6_hand.version.get_device_info()

        assert info.timestamp > 0, "timestamp should be positive"
        assert info.timestamp <= time.time(), "timestamp should not be in the future"

    def test_timestamp_progression_and_full_validation(self, l6_hand: L6):
        """Two consecutive calls should have increasing timestamps; second fully validated."""
        info1 = l6_hand.version.get_device_info()
        time.sleep(0.2)
        info2 = l6_hand.version.get_device_info()

        assert info2.timestamp > info1.timestamp, (
            f"Second timestamp ({info2.timestamp:.3f}) should be > first ({info1.timestamp:.3f})"
        )

        assert isinstance(info2, DeviceInfo), "Expected a DeviceInfo instance"
        assert info2.serial_number is not None, "serial_number should not be None"
        assert len(info2.serial_number) > 0, "serial_number should not be empty"

        for label, version in [
            ("pcb_version", info2.pcb_version),
            ("firmware_version", info2.firmware_version),
            ("mechanical_version", info2.mechanical_version),
        ]:
            assert isinstance(version, Version), f"{label} should be a Version instance"
            assert version.major >= 0, f"{label}.major should be non-negative"
            assert version.minor >= 0, f"{label}.minor should be non-negative"
            assert version.patch >= 0, f"{label}.patch should be non-negative"

        print(f"\n  Serial Number:      {info2.serial_number}")
        print(f"  PCB Version:        {info2.pcb_version}")
        print(f"  Firmware Version:   {info2.firmware_version}")
        print(f"  Mechanical Version: {info2.mechanical_version}")
        print(f"  Timestamp delta:    {info2.timestamp - info1.timestamp:.3f}s")
