"""Tests for L25 VersionManager with hardware."""

import time

import pytest

from linkerbot import L25
from linkerbot.hand.l25 import DeviceInfo, Version

pytestmark = [pytest.mark.l25, pytest.mark.lifecycle]


class TestDeviceInfo:
    """Test reading device information from real hardware."""

    def test_get_device_info_returns_complete(self, l25_hand: L25):
        """get_device_info should return a DeviceInfo with all fields populated."""
        info = l25_hand.version.get_device_info()

        assert isinstance(info, DeviceInfo), "Expected a DeviceInfo instance"
        assert info.serial_number is not None, "serial_number should not be None"
        assert info.pcb_version is not None, "pcb_version should not be None"
        assert info.firmware_version is not None, "firmware_version should not be None"
        assert info.mechanical_version is not None, (
            "mechanical_version should not be None"
        )

        print(f"\n  Serial number: {info.serial_number}")
        print(f"  PCB version: {info.pcb_version}")
        print(f"  Firmware version: {info.firmware_version}")
        print(f"  Mechanical version: {info.mechanical_version}")

    def test_serial_number_format(self, l25_hand: L25):
        """serial_number should be a non-empty string of reasonable length."""
        info = l25_hand.version.get_device_info()

        assert isinstance(info.serial_number, str), "serial_number should be a string"
        assert len(info.serial_number) > 0, "serial_number should not be empty"
        assert len(info.serial_number) < 100, (
            "serial_number should be less than 100 chars"
        )

    def test_version_format(self, l25_hand: L25):
        """pcb, firmware, and mechanical versions should have non-negative integer fields."""
        info = l25_hand.version.get_device_info()

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

    def test_device_info_has_timestamp(self, l25_hand: L25):
        """timestamp should be a positive value no later than now."""
        info = l25_hand.version.get_device_info()

        assert info.timestamp > 0, "timestamp should be positive"
        assert info.timestamp <= time.time(), "timestamp should not be in the future"
