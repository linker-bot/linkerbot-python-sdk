"""Version information and serial number management for L6 robotic hand.

This module provides the VersionManager class for reading device version information
and managing serial numbers.
"""

import time
from collections.abc import Mapping
from dataclasses import dataclass, field

import can

from linkerbot.comm import CANMessageDispatcher
from linkerbot.exceptions import TimeoutError, ValidationError
from linkerbot.relay import DataRelay


@dataclass(frozen=True)
class Version:
    """Version number in semantic versioning format.

    Attributes:
        major: Major version number.
        minor: Minor version number.
        patch: Patch/revision number.
    """

    major: int
    minor: int
    patch: int

    def __str__(self) -> str:
        """Return version string in format 'V{major}.{minor}.{patch}'."""
        return f"V{self.major}.{self.minor}.{self.patch}"


@dataclass(frozen=True)
class DeviceInfo:
    """Complete device information including version numbers and serial number.

    Attributes:
        serial_number: Device serial number (e.g., 'LHL6-03-001-L-Z-1-A').
        pcb_version: PCB hardware version.
        firmware_version: Embedded firmware version.
        mechanical_version: Mechanical structure version.
        timestamp: Unix timestamp when the data was retrieved.
    """

    serial_number: str
    pcb_version: Version
    firmware_version: Version
    mechanical_version: Version
    timestamp: float


@dataclass(frozen=True)
class SerialNumberFrames:
    """Internal helper for accumulating serial number frames."""

    frames: Mapping[int, bytes] = field(default_factory=dict)
    started_at: float = field(default_factory=time.time)

    def add_frame(self, frame_id: int, data: bytes) -> "SerialNumberFrames":
        new_frames = {**self.frames, frame_id: data}
        return SerialNumberFrames(frames=new_frames, started_at=self.started_at)

    def is_complete(self) -> bool:
        # Internal: Check if all frames received
        return len(self.frames) == 4 and all(i in self.frames for i in range(0, 4))

    def assemble(self) -> str:
        # Internal: Assemble and decode
        data = bytearray()
        for i in range(0, 4):
            data.extend(self.frames[i])
        return data.rstrip(b"\x00").decode("ascii", errors="ignore")


class VersionManager:
    """Manager for device version information and serial number configuration.

    This class provides methods to read device information including serial number,
    PCB version, firmware version, and mechanical version. It also supports
    setting the device serial number with password authentication.
    """

    _SN_CMD = 0xC0
    _PCB_VERSION_CMD = 0xC1
    _FIRMWARE_VERSION_CMD = 0xC2
    _MECHANICAL_VERSION_CMD = 0xC4
    _PASSWORD_CMD = 0xCB
    _SAVE_CMD = 0xCF

    def __init__(self, arbitration_id: int, dispatcher: CANMessageDispatcher) -> None:
        """Initialize the version manager.

        Args:
            arbitration_id: Arbitration ID for version information requests.
            dispatcher: Message dispatcher for communication.
        """
        self._arbitration_id = arbitration_id
        self._dispatcher = dispatcher
        self._dispatcher.subscribe(self._on_message)

        # Serial number frame assembly
        self._sn_frames: SerialNumberFrames | None = None
        self._sn_relay = DataRelay[str]()

        # Version number relays
        self._pcb_relay = DataRelay[Version]()
        self._firmware_relay = DataRelay[Version]()
        self._mechanical_relay = DataRelay[Version]()

        # Password verification and save operation
        self._password_relay = DataRelay[bool]()
        self._save_relay = DataRelay[bool]()

    def get_device_info(self, timeout_ms: float = 1000) -> DeviceInfo:
        """Get complete device information including all version numbers and serial number.

        This method requests and waits for all device information: serial number,
        PCB version, firmware version, and mechanical version.

        Args:
            timeout_ms: Maximum time to wait for each request in milliseconds (default: 1000).

        Returns:
            DeviceInfo containing all device information.

        Raises:
            TimeoutError: If any request times out.
            ValidationError: If timeout_ms is not positive.

        Example:
            >>> manager = VersionManager(arbitration_id, dispatcher)
            >>> info = manager.get_device_info()
            >>> print(f"Serial Number: {info.serial_number}")
            >>> print(f"PCB Version: {info.pcb_version}")
            >>> print(f"Firmware Version: {info.firmware_version}")
            >>> print(f"Mechanical Version: {info.mechanical_version}")
        """
        if timeout_ms <= 0:
            raise ValidationError("timeout_ms must be positive")

        sn = self._get_serial_number_blocking(timeout_ms)
        pcb_ver = self._get_pcb_version_blocking(timeout_ms)
        fw_ver = self._get_firmware_version_blocking(timeout_ms)
        mech_ver = self._get_mechanical_version_blocking(timeout_ms)

        return DeviceInfo(
            serial_number=sn,
            pcb_version=pcb_ver,
            firmware_version=fw_ver,
            mechanical_version=mech_ver,
            timestamp=time.time(),
        )

    def set_serial_number(
        self, serial_number: str, password: list[int], timeout_ms: float = 200
    ) -> None:
        """Set device serial number with password authentication.

        This method sets the device serial number. Password verification is required
        before the serial number can be modified. The serial number is automatically
        saved to non-volatile memory after being set.

        Args:
            serial_number: New serial number string (ASCII format).
            password: 6-byte password list (default: [0x06, 0x05, 0x04, 0x03, 0x02, 0x01]).
            timeout_ms: Maximum time to wait for confirmation in milliseconds (default: 200).

        Raises:
            TimeoutError: If password verification or setting fails.
            ValidationError: If password length is not 6 or timeout_ms is not positive.

        Example:
            >>> manager = VersionManager(arbitration_id, dispatcher)
            >>> # Set serial number with default password
            >>> manager.set_serial_number(
            ...     serial_number="LHL6-03-001-L-Z-1-A",
            ...     password=[0x06, 0x05, 0x04, 0x03, 0x02, 0x01]
            ... )
        """
        if timeout_ms <= 0:
            raise ValidationError("timeout_ms must be positive")

        if len(password) != 6:
            raise ValidationError(f"Password must be 6 bytes, got {len(password)}")

        self._verify_password(password, timeout_ms)
        # TODO: Add validation for serial number format and length
        self._send_serial_number(serial_number)
        self._save_parameters()

    def _save_parameters(self, timeout_ms: float = 200) -> None:
        """Save current device configuration to non-volatile memory.

        This method sends a save command to persist the current device
        configuration (serial number and version information) so they are
        retained after power cycling.

        Args:
            timeout_ms: Maximum time to wait for save confirmation in milliseconds (default: 200).

        Raises:
            TimeoutError: If no confirmation is received within timeout.
            ValidationError: If timeout_ms is not positive.

        Example:
            >>> manager = VersionManager(arbitration_id, dispatcher)
            >>> # Set serial number
            >>> manager.set_serial_number(
            ...     serial_number="LHL6-03-001-L-Z-1-A",
            ...     password=[0x06, 0x05, 0x04, 0x03, 0x02, 0x01]
            ... )
            >>> # Save to non-volatile memory
            >>> try:
            ...     manager.save_parameters()
            ...     print("Configuration saved successfully")
            ... except TimeoutError:
            ...     print("Save operation timed out")
        """
        if timeout_ms <= 0:
            raise ValidationError("timeout_ms must be positive")

        # Send save command (8 bytes, all 0xCF)
        data = [self._SAVE_CMD] * 8
        msg = can.Message(
            arbitration_id=self._arbitration_id,
            data=data,
            is_extended_id=False,
        )
        self._dispatcher.send(msg)
        self._save_relay.wait(timeout_ms / 1000.0)

    def _get_serial_number_blocking(self, timeout_ms: float) -> str:
        msg = can.Message(
            arbitration_id=self._arbitration_id,
            data=[self._SN_CMD],
            is_extended_id=False,
        )
        self._dispatcher.send(msg)
        return self._sn_relay.wait(timeout_ms / 1000.0)

    def _get_pcb_version_blocking(self, timeout_ms: float) -> Version:
        msg = can.Message(
            arbitration_id=self._arbitration_id,
            data=[self._PCB_VERSION_CMD, 0x01],
            is_extended_id=False,
        )
        self._dispatcher.send(msg)
        return self._pcb_relay.wait(timeout_ms / 1000.0)

    def _get_firmware_version_blocking(self, timeout_ms: float) -> Version:
        msg = can.Message(
            arbitration_id=self._arbitration_id,
            data=[self._FIRMWARE_VERSION_CMD],
            is_extended_id=False,
        )
        self._dispatcher.send(msg)
        return self._firmware_relay.wait(timeout_ms / 1000.0)

    def _get_mechanical_version_blocking(self, timeout_ms: float) -> Version:
        msg = can.Message(
            arbitration_id=self._arbitration_id,
            data=[self._MECHANICAL_VERSION_CMD],
            is_extended_id=False,
        )
        self._dispatcher.send(msg)
        return self._mechanical_relay.wait(timeout_ms / 1000.0)

    def _verify_password(self, password: list[int], timeout_ms: float) -> None:
        data = [self._PASSWORD_CMD, *password]
        msg = can.Message(
            arbitration_id=self._arbitration_id,
            data=data,
            is_extended_id=False,
        )
        self._dispatcher.send(msg)
        result = self._password_relay.wait(timeout_ms / 1000.0)
        if not result:
            raise TimeoutError("Password verification failed")

    def _send_serial_number(self, serial_number: str) -> None:
        # Internal: Send serial number
        sn_bytes = serial_number.encode("ascii")
        sn_padded = sn_bytes + b"\x00" * (24 - len(sn_bytes))

        for frame_id in range(4):
            start_idx = frame_id * 6
            frame_data = sn_padded[start_idx : start_idx + 6]
            data = [self._SN_CMD, frame_id, *frame_data]

            msg = can.Message(
                arbitration_id=self._arbitration_id,
                data=data,
                is_extended_id=False,
            )
            self._dispatcher.send(msg)
            time.sleep(0.001)

    def _on_message(self, msg: can.Message) -> None:
        # Internal callback
        if msg.arbitration_id != self._arbitration_id:
            return

        if len(msg.data) < 1:
            return

        cmd = msg.data[0]

        match cmd:
            case self._SN_CMD if len(msg.data) == 8 or len(msg.data) == 3:
                frame_id = msg.data[1]
                frame_data = bytes(msg.data[2:8])

                if self._sn_frames is None:
                    self._sn_frames = SerialNumberFrames()

                self._sn_frames = self._sn_frames.add_frame(frame_id, frame_data)

                if self._sn_frames.is_complete():
                    sn = self._sn_frames.assemble()
                    self._sn_frames = None
                    self._sn_relay.push(sn)

            case self._PCB_VERSION_CMD if len(msg.data) >= 5:
                if msg.data[1] == 0x01:
                    version = Version(
                        major=msg.data[2], minor=msg.data[3], patch=msg.data[4]
                    )
                    self._pcb_relay.push(version)

            case self._FIRMWARE_VERSION_CMD if len(msg.data) >= 4:
                version = Version(
                    major=msg.data[1], minor=msg.data[2], patch=msg.data[3]
                )
                self._firmware_relay.push(version)

            case self._MECHANICAL_VERSION_CMD if len(msg.data) >= 4:
                version = Version(
                    major=msg.data[1], minor=msg.data[2], patch=msg.data[3]
                )
                self._mechanical_relay.push(version)

            case self._PASSWORD_CMD:
                success = len(msg.data) >= 7
                self._password_relay.push(success)

            case self._SAVE_CMD if len(msg.data) >= 2:
                if msg.data[1] == 0x01:
                    self._save_relay.push(True)
