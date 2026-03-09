"""Version information and serial number management for L25 robotic hand.

This module provides the VersionManager class for reading device version information.
"""

import time
from collections.abc import Mapping
from dataclasses import dataclass, field

import can

from linkerbot.comm import CANMessageDispatcher
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
        serial_number: Device serial number.
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
    """Manager for device version information.

    This class provides methods to read device information including serial number,
    PCB version, firmware version, and mechanical version.
    """

    _SN_CMD = 0xC0
    _PCB_VERSION_CMD = 0xC1
    _FIRMWARE_VERSION_CMD = 0xC2
    _MECHANICAL_VERSION_CMD = 0xC4

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
        self._sn_in_flight = False
        self._sn_in_flight_since: float = 0
        self._sn_relay = DataRelay[str]()

        # Version number relays
        self._pcb_relay = DataRelay[Version]()
        self._firmware_relay = DataRelay[Version]()
        self._mechanical_relay = DataRelay[Version]()

    _QUERY_TIMEOUT_MS: float = 20

    def get_device_info(self) -> DeviceInfo:
        """Get complete device information including all version numbers and serial number.

        Queries are sent sequentially to avoid overwhelming the device firmware.

        Returns:
            DeviceInfo containing all device information.

        Raises:
            TimeoutError: If any request times out.

        Example:
            >>> manager = VersionManager(arbitration_id, dispatcher)
            >>> info = manager.get_device_info()
            >>> print(f"Serial Number: {info.serial_number}")
            >>> print(f"PCB Version: {info.pcb_version}")
            >>> print(f"Firmware Version: {info.firmware_version}")
            >>> print(f"Mechanical Version: {info.mechanical_version}")
        """
        timeout = self._QUERY_TIMEOUT_MS

        fw = self._get_firmware_version_blocking(timeout)
        mech = self._get_mechanical_version_blocking(timeout)
        pcb = self._get_pcb_version_blocking(timeout)
        sn = self._get_serial_number_blocking(timeout)

        return DeviceInfo(
            serial_number=sn,
            pcb_version=pcb,
            firmware_version=fw,
            mechanical_version=mech,
            timestamp=time.time(),
        )

    def _get_serial_number_blocking(self, timeout_ms: float) -> str:
        self._sn_frames = None
        self._sn_in_flight = False
        msg = can.Message(
            arbitration_id=self._arbitration_id,
            data=[self._SN_CMD],
            is_extended_id=False,
        )
        self._sn_in_flight = True
        self._sn_in_flight_since = time.monotonic()
        self._dispatcher.send(msg)
        return self._sn_relay.wait(timeout_ms / 1000.0)

    def _get_pcb_version_blocking(self, timeout_ms: float) -> Version:
        msg = can.Message(
            arbitration_id=self._arbitration_id,
            data=[self._PCB_VERSION_CMD],
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

    def _on_message(self, msg: can.Message) -> None:
        # Internal callback
        if msg.arbitration_id != self._arbitration_id:
            return

        if len(msg.data) < 1:
            return

        cmd = msg.data[0]

        match cmd:
            case self._SN_CMD if len(msg.data) >= 2:
                frame_id = msg.data[1]
                frame_data = bytes(msg.data[2:8])

                if self._sn_frames is None:
                    self._sn_frames = SerialNumberFrames()

                self._sn_frames = self._sn_frames.add_frame(frame_id, frame_data)

                if self._sn_frames.is_complete():
                    sn = self._sn_frames.assemble()
                    self._sn_in_flight = False
                    self._sn_frames = None
                    self._sn_relay.push(sn)

            case self._PCB_VERSION_CMD if len(msg.data) >= 4:
                version = Version(
                    major=msg.data[1], minor=msg.data[2], patch=msg.data[3]
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
