"""Version information and serial number management for O6 robotic hand.

This module provides the VersionManager class for reading device version information.
"""

import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass, field

import can

from linkerbot.comm import CANMessageDispatcher
from linkerbot.exceptions import TimeoutError, ValidationError


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
        serial_number: Device serial number (e.g., 'LHO6-03-123-L-B-1-A').
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
    """Internal helper for accumulating serial number frames.

    O6 uses byte index as frame identifier (0, 6, 12, 18) instead of
    sequential frame numbers like L6.
    """

    # Expected byte indices for O6 serial number frames
    _EXPECTED_INDICES: tuple[int, ...] = (0, 6, 12, 18)

    frames: Mapping[int, bytes] = field(default_factory=dict)
    started_at: float = field(default_factory=time.time)

    def add_frame(self, byte_index: int, data: bytes) -> "SerialNumberFrames":
        new_frames = {**self.frames, byte_index: data}
        return SerialNumberFrames(frames=new_frames, started_at=self.started_at)

    def is_complete(self) -> bool:
        # Internal: Check if all frames received (byte indices: 0, 6, 12, 18)
        return len(self.frames) == 4 and all(
            i in self.frames for i in self._EXPECTED_INDICES
        )

    def assemble(self) -> str:
        # Internal: Assemble using byte indices and decode
        data = bytearray(24)
        for byte_index, frame_data in self.frames.items():
            for i, b in enumerate(frame_data):
                if byte_index + i < 24:
                    data[byte_index + i] = b
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
        self._sn_complete: str | None = None
        self._sn_waiters: list[tuple[threading.Event, dict]] = []
        self._sn_lock = threading.Lock()

        # Version number responses
        self._pcb_version: Version | None = None
        self._pcb_waiters: list[tuple[threading.Event, dict]] = []
        self._pcb_lock = threading.Lock()

        self._firmware_version: Version | None = None
        self._firmware_waiters: list[tuple[threading.Event, dict]] = []
        self._firmware_lock = threading.Lock()

        self._mechanical_version: Version | None = None
        self._mechanical_waiters: list[tuple[threading.Event, dict]] = []
        self._mechanical_lock = threading.Lock()

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

    def _get_serial_number_blocking(self, timeout_ms: float) -> str:
        event = threading.Event()
        result_holder: dict[str, str | None] = {"data": None}

        with self._sn_lock:
            self._sn_waiters.append((event, result_holder))

        # Send request
        msg = can.Message(
            arbitration_id=self._arbitration_id,
            data=[self._SN_CMD],
            is_extended_id=False,
        )
        self._dispatcher.send(msg)

        # Wait for response
        if event.wait(timeout_ms / 1000.0):
            if result_holder["data"] is None:
                raise TimeoutError(f"Serial number not received within {timeout_ms}ms")
            return result_holder["data"]
        else:
            with self._sn_lock:
                if (event, result_holder) in self._sn_waiters:
                    self._sn_waiters.remove((event, result_holder))
            raise TimeoutError(f"Serial number request timed out after {timeout_ms}ms")

    def _get_pcb_version_blocking(self, timeout_ms: float) -> Version:
        event = threading.Event()
        result_holder: dict[str, Version | None] = {"data": None}

        with self._pcb_lock:
            self._pcb_waiters.append((event, result_holder))

        # Send request (O6 only sends command byte, no extra 0x01)
        msg = can.Message(
            arbitration_id=self._arbitration_id,
            data=[self._PCB_VERSION_CMD],
            is_extended_id=False,
        )
        self._dispatcher.send(msg)

        # Wait for response
        if event.wait(timeout_ms / 1000.0):
            if result_holder["data"] is None:
                raise TimeoutError(f"PCB version not received within {timeout_ms}ms")
            return result_holder["data"]
        else:
            with self._pcb_lock:
                if (event, result_holder) in self._pcb_waiters:
                    self._pcb_waiters.remove((event, result_holder))
            raise TimeoutError(f"PCB version request timed out after {timeout_ms}ms")

    def _get_firmware_version_blocking(self, timeout_ms: float) -> Version:
        event = threading.Event()
        result_holder: dict[str, Version | None] = {"data": None}

        with self._firmware_lock:
            self._firmware_waiters.append((event, result_holder))

        # Send request
        msg = can.Message(
            arbitration_id=self._arbitration_id,
            data=[self._FIRMWARE_VERSION_CMD],
            is_extended_id=False,
        )
        self._dispatcher.send(msg)

        # Wait for response
        if event.wait(timeout_ms / 1000.0):
            if result_holder["data"] is None:
                raise TimeoutError(
                    f"Firmware version not received within {timeout_ms}ms"
                )
            return result_holder["data"]
        else:
            with self._firmware_lock:
                if (event, result_holder) in self._firmware_waiters:
                    self._firmware_waiters.remove((event, result_holder))
            raise TimeoutError(
                f"Firmware version request timed out after {timeout_ms}ms"
            )

    def _get_mechanical_version_blocking(self, timeout_ms: float) -> Version:
        event = threading.Event()
        result_holder: dict[str, Version | None] = {"data": None}

        with self._mechanical_lock:
            self._mechanical_waiters.append((event, result_holder))

        # Send request
        msg = can.Message(
            arbitration_id=self._arbitration_id,
            data=[self._MECHANICAL_VERSION_CMD],
            is_extended_id=False,
        )
        self._dispatcher.send(msg)

        # Wait for response
        if event.wait(timeout_ms / 1000.0):
            if result_holder["data"] is None:
                raise TimeoutError(
                    f"Mechanical version not received within {timeout_ms}ms"
                )
            return result_holder["data"]
        else:
            with self._mechanical_lock:
                if (event, result_holder) in self._mechanical_waiters:
                    self._mechanical_waiters.remove((event, result_holder))
            raise TimeoutError(
                f"Mechanical version request timed out after {timeout_ms}ms"
            )

    def _on_message(self, msg: can.Message) -> None:
        # Internal callback
        if msg.arbitration_id != self._arbitration_id:
            return

        if len(msg.data) < 1:
            return

        cmd = msg.data[0]

        match cmd:
            case self._SN_CMD if len(msg.data) >= 2:
                # Serial number frame: 0xC0 + byte_index + 6 bytes data
                # O6 uses byte index (0, 6, 12, 18) instead of sequential frame ID
                byte_index = msg.data[1]
                frame_data = bytes(msg.data[2:8])

                if self._sn_frames is None:
                    self._sn_frames = SerialNumberFrames()

                self._sn_frames = self._sn_frames.add_frame(byte_index, frame_data)

                if self._sn_frames.is_complete():
                    sn = self._sn_frames.assemble()
                    self._sn_frames = None

                    with self._sn_lock:
                        for event, result_holder in self._sn_waiters:
                            result_holder["data"] = sn
                            event.set()
                        self._sn_waiters.clear()

            case self._PCB_VERSION_CMD if len(msg.data) >= 4:
                # O6 format: 0xC1 + major + minor + patch
                version = Version(
                    major=msg.data[1], minor=msg.data[2], patch=msg.data[3]
                )
                with self._pcb_lock:
                    for event, result_holder in self._pcb_waiters:
                        result_holder["data"] = version
                        event.set()
                    self._pcb_waiters.clear()

            case self._FIRMWARE_VERSION_CMD if len(msg.data) >= 4:
                version = Version(
                    major=msg.data[1], minor=msg.data[2], patch=msg.data[3]
                )
                with self._firmware_lock:
                    for event, result_holder in self._firmware_waiters:
                        result_holder["data"] = version
                        event.set()
                    self._firmware_waiters.clear()

            case self._MECHANICAL_VERSION_CMD if len(msg.data) >= 4:
                version = Version(
                    major=msg.data[1], minor=msg.data[2], patch=msg.data[3]
                )
                with self._mechanical_lock:
                    for event, result_holder in self._mechanical_waiters:
                        result_holder["data"] = version
                        event.set()
                    self._mechanical_waiters.clear()
