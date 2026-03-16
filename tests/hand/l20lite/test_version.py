"""Tests for L20Lite VersionManager with hardware."""

import time

import pytest

from linkerbot import L20lite
from linkerbot.hand.l20lite import DeviceInfo, Version

pytestmark = [pytest.mark.l20lite, pytest.mark.lifecycle]


class TestDeviceInfo:
    """Test reading device information from real hardware."""

    def test_device_info_returns_complete(self, l20lite_hand: L20lite):
        """get_device_info should return a DeviceInfo with all fields populated."""
        info = l20lite_hand.version.get_device_info()

        assert isinstance(info, DeviceInfo)
        assert info.serial_number is not None
        assert info.pcb_version is not None
        assert info.firmware_version is not None
        assert info.mechanical_version is not None

    def test_serial_number_format(self, l20lite_hand: L20lite):
        """serial_number should be a non-empty string of reasonable length."""
        info = l20lite_hand.version.get_device_info()

        assert isinstance(info.serial_number, str)
        assert len(info.serial_number) > 0
        assert len(info.serial_number) < 100

    def test_version_format(self, l20lite_hand: L20lite):
        """pcb, firmware, and mechanical versions should have non-negative integer fields."""
        info = l20lite_hand.version.get_device_info()

        for label, version in [
            ("pcb_version", info.pcb_version),
            ("firmware_version", info.firmware_version),
            ("mechanical_version", info.mechanical_version),
        ]:
            assert isinstance(version, Version), f"{label} should be a Version instance"
            assert isinstance(version.major, int) and version.major >= 0
            assert isinstance(version.minor, int) and version.minor >= 0
            assert isinstance(version.patch, int) and version.patch >= 0

    def test_device_info_has_timestamp(self, l20lite_hand: L20lite):
        """timestamp should be a positive value no later than now."""
        info = l20lite_hand.version.get_device_info()

        assert info.timestamp > 0
        assert info.timestamp <= time.time()

    def test_timestamp_progression_and_full_validation(self, l20lite_hand: L20lite):
        """Two consecutive calls should have increasing timestamps; second fully validated."""
        info1 = l20lite_hand.version.get_device_info()
        time.sleep(0.2)
        info2 = l20lite_hand.version.get_device_info()

        assert info2.timestamp > info1.timestamp, (
            f"Second timestamp ({info2.timestamp:.3f}) should be > first ({info1.timestamp:.3f})"
        )

        assert isinstance(info2, DeviceInfo)
        assert info2.serial_number is not None
        assert len(info2.serial_number) > 0

        for label, version in [
            ("pcb_version", info2.pcb_version),
            ("firmware_version", info2.firmware_version),
            ("mechanical_version", info2.mechanical_version),
        ]:
            assert isinstance(version, Version), f"{label} should be Version"
            assert version.major >= 0
            assert version.minor >= 0
            assert version.patch >= 0

        print(f"\n  Serial Number:      {info2.serial_number}")
        print(f"  PCB Version:        {info2.pcb_version}")
        print(f"  Firmware Version:   {info2.firmware_version}")
        print(f"  Mechanical Version: {info2.mechanical_version}")
        print(f"  Timestamp delta:    {info2.timestamp - info1.timestamp:.3f}s")
