"""ctypes wrapper for the vendor CANFD dynamic library."""

import ctypes
import os
import platform
import threading
from pathlib import Path
from typing import Any

from linkerbot.exceptions import CANError, ValidationError

from .types import CANFDConfigOptions, CANFDMessage, dlc_to_length

CANFD_DEFAULT_SEND_TIMEOUT_MS = 10
CANFD_DEFAULT_RECEIVE_TIMEOUT_MS = 10
CANFD_DEFAULT_MAX_RECEIVE_FRAMES = 64
CANFD_TRANSMIT_FRAME_COUNT = 1
CANFD_EXTENDED_FRAME_FLAG = 1
CANFD_STANDARD_FRAME_FLAG = 0
CANFD_REMOTE_FRAME_DISABLED = 0
CANFD_STATUS_OK = 0
CANFD_SCAN_NO_DEVICE = 0
_DEV_INFO_FIELD_LENGTH = 32
_C_STRING_TERMINATOR = b"\x00"
_ENV_LIBRARY_PATH = "LINKERBOT_CANFD_LIB"
_LINUX_LIBRARY_NAME = "libcanbus.so"
_WINDOWS_LIBRARY_NAME = "HCanbus.dll"
_LINUX_USB_LIBRARY_NAME = "libusb-1.0.so.0"


class CanFDConfig(ctypes.Structure):
    """Vendor CANFD initialization structure."""

    _fields_ = [
        ("NomBaud", ctypes.c_uint),
        ("DatBaud", ctypes.c_uint),
        ("NomPre", ctypes.c_ushort),
        ("NomTseg1", ctypes.c_ubyte),
        ("NomTseg2", ctypes.c_ubyte),
        ("NomSJW", ctypes.c_ubyte),
        ("DatPre", ctypes.c_ubyte),
        ("DatTseg1", ctypes.c_ubyte),
        ("DatTseg2", ctypes.c_ubyte),
        ("DatSJW", ctypes.c_ubyte),
        ("Config", ctypes.c_ubyte),
        ("Model", ctypes.c_ubyte),
        ("Cantype", ctypes.c_ubyte),
    ]


class CanFDMsg(ctypes.Structure):
    """Vendor CANFD frame structure."""

    _fields_ = [
        ("ID", ctypes.c_uint),
        ("TimeStamp", ctypes.c_uint),
        ("FrameType", ctypes.c_ubyte),
        ("DLC", ctypes.c_ubyte),
        ("ExternFlag", ctypes.c_ubyte),
        ("RemoteFlag", ctypes.c_ubyte),
        ("BusSatus", ctypes.c_ubyte),
        ("ErrSatus", ctypes.c_ubyte),
        ("TECounter", ctypes.c_ubyte),
        ("RECounter", ctypes.c_ubyte),
        ("Data", ctypes.c_ubyte * 64),
    ]


class DevInfo(ctypes.Structure):
    """USB-CANFD adapter information returned by the vendor library."""

    _fields_ = [
        ("HW_Type", ctypes.c_char * _DEV_INFO_FIELD_LENGTH),
        ("HW_Ser", ctypes.c_char * _DEV_INFO_FIELD_LENGTH),
        ("HW_Ver", ctypes.c_char * _DEV_INFO_FIELD_LENGTH),
        ("FW_Ver", ctypes.c_char * _DEV_INFO_FIELD_LENGTH),
        ("MF_Date", ctypes.c_char * _DEV_INFO_FIELD_LENGTH),
    ]


class CANFDInterface:
    """Low-level CANFD interface backed by libcanbus.so or HCanbus.dll."""

    def __init__(
        self,
        device_index: int = 0,
        channel_index: int = 0,
        library_path: str | Path | None = None,
        config: CANFDConfigOptions | None = None,
    ) -> None:
        """Open and initialize a CANFD adapter channel."""
        if device_index < 0:
            raise ValidationError("device_index must be non-negative")
        if channel_index < 0:
            raise ValidationError("channel_index must be non-negative")

        self._device_index = device_index
        self._channel_index = channel_index
        self._config = config or CANFDConfigOptions()
        self._lock = threading.Lock()
        self._closed = True
        self._lib = _load_library(library_path)
        _bind_signatures(self._lib)
        self._open()

    @property
    def device_index(self) -> int:
        """Adapter device index passed to the vendor library."""
        return self._device_index

    @property
    def channel_index(self) -> int:
        """CANFD channel index passed to the vendor library."""
        return self._channel_index

    @property
    def config(self) -> CANFDConfigOptions:
        """CANFD configuration used to initialize this interface."""
        return self._config

    def _open(self) -> None:
        with self._lock:
            count = self._lib.CAN_ScanDevice()
            if count < CANFD_SCAN_NO_DEVICE:
                raise CANError(f"CAN_ScanDevice failed with status {count}")
            if count == CANFD_SCAN_NO_DEVICE:
                raise CANError("No CANFD adapter found")
            if self._device_index >= count:
                raise CANError(
                    f"CANFD device_index {self._device_index} out of range; found {count} adapter(s)"
                )

            status = self._lib.CAN_OpenDevice(self._device_index, self._channel_index)
            if status != CANFD_STATUS_OK:
                raise CANError(f"CAN_OpenDevice failed with status {status}")
            self._closed = False

            config = self._build_ctypes_config()
            status = self._lib.CANFD_Init(
                self._device_index, self._channel_index, ctypes.byref(config)
            )
            if status != CANFD_STATUS_OK:
                try:
                    self._lib.CAN_CloseDevice(self._device_index, self._channel_index)
                finally:
                    self._closed = True
                raise CANError(f"CANFD_Init failed with status {status}")

    def _build_ctypes_config(self) -> CanFDConfig:
        return CanFDConfig(
            NomBaud=self._config.nom_baud,
            DatBaud=self._config.dat_baud,
            NomPre=0,
            NomTseg1=0,
            NomTseg2=0,
            NomSJW=0,
            DatPre=0,
            DatTseg1=0,
            DatTseg2=0,
            DatSJW=0,
            Config=self._config.config,
            Model=self._config.model,
            Cantype=self._config.cantype,
        )

    def send(
        self,
        message: CANFDMessage,
        timeout_ms: int = CANFD_DEFAULT_SEND_TIMEOUT_MS,
    ) -> None:
        """Transmit one CANFD frame through the vendor library."""
        if timeout_ms < 0:
            raise ValidationError("timeout_ms must be non-negative")
        with self._lock:
            self._ensure_open()
            frame = self._message_to_frame(message)
            sent = self._lib.CANFD_Transmit(
                self._device_index,
                self._channel_index,
                ctypes.byref(frame),
                CANFD_TRANSMIT_FRAME_COUNT,
                timeout_ms,
            )
            if sent <= 0:
                raise CANError(f"CANFD_Transmit failed with status {sent}")

    def receive(
        self,
        max_frames: int = CANFD_DEFAULT_MAX_RECEIVE_FRAMES,
        timeout_ms: int = CANFD_DEFAULT_RECEIVE_TIMEOUT_MS,
    ) -> list[CANFDMessage]:
        """Receive up to max_frames CANFD frames from the vendor library."""
        if max_frames <= 0:
            raise ValidationError("max_frames must be positive")
        if timeout_ms < 0:
            raise ValidationError("timeout_ms must be non-negative")

        with self._lock:
            self._ensure_open()
            buffer = (CanFDMsg * max_frames)()
            received = self._lib.CANFD_Receive(
                self._device_index,
                self._channel_index,
                buffer,
                max_frames,
                timeout_ms,
            )
            if received < CANFD_STATUS_OK:
                raise CANError(f"CANFD_Receive failed with status {received}")
            if received == CANFD_STATUS_OK:
                return []
            return [self._frame_to_message(buffer[i]) for i in range(received)]

    def read_dev_info(self) -> dict[str, str]:
        """Read USB-CANFD adapter information from the vendor library."""
        with self._lock:
            self._ensure_open()
            info = DevInfo()
            status = self._lib.CAN_ReadDevInfo(self._device_index, ctypes.byref(info))
            if status != CANFD_STATUS_OK:
                raise CANError(f"CAN_ReadDevInfo failed with status {status}")
            return {
                "hw_type": _decode_c_string(info.HW_Type),
                "hw_serial": _decode_c_string(info.HW_Ser),
                "hw_version": _decode_c_string(info.HW_Ver),
                "fw_version": _decode_c_string(info.FW_Ver),
                "manufacture_date": _decode_c_string(info.MF_Date),
            }

    def close(self) -> None:
        """Close the CANFD adapter channel."""
        with self._lock:
            if self._closed:
                return
            status = self._lib.CAN_CloseDevice(self._device_index, self._channel_index)
            self._closed = True
            if status != CANFD_STATUS_OK:
                raise CANError(f"CAN_CloseDevice failed with status {status}")

    def _ensure_open(self) -> None:
        if self._closed:
            raise CANError("CANFD interface is closed")

    def _message_to_frame(self, message: CANFDMessage) -> CanFDMsg:
        frame = CanFDMsg()
        frame.ID = message.arbitration_id
        frame.TimeStamp = 0
        frame.FrameType = (
            message.frame_type
            if message.frame_type is not None
            else self._config.frame_type
        )
        frame.DLC = message.dlc or 0
        frame.ExternFlag = (
            CANFD_EXTENDED_FRAME_FLAG
            if message.is_extended_id
            else CANFD_STANDARD_FRAME_FLAG
        )
        frame.RemoteFlag = CANFD_REMOTE_FRAME_DISABLED
        frame.BusSatus = CANFD_STATUS_OK
        frame.ErrSatus = CANFD_STATUS_OK
        frame.TECounter = 0
        frame.RECounter = 0
        for index, value in enumerate(message.data):
            frame.Data[index] = value
        return frame

    def _frame_to_message(self, frame: CanFDMsg) -> CANFDMessage:
        length = dlc_to_length(frame.DLC)
        return CANFDMessage(
            arbitration_id=frame.ID,
            data=bytes(frame.Data[:length]),
            dlc=frame.DLC,
            is_extended_id=bool(frame.ExternFlag),
            frame_type=frame.FrameType,
            timestamp=frame.TimeStamp,
        )

    def __enter__(self) -> "CANFDInterface":
        """Enter the context manager."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit the context manager and close the CANFD interface."""
        self.close()


def _load_library(library_path: str | Path | None) -> Any:
    _preload_vendor_dependencies()
    errors: list[str] = []
    for candidate in _library_candidates(library_path):
        try:
            return _ctypes_loader()(str(candidate))
        except OSError as error:
            errors.append(f"{candidate}: {error}")

    attempted = "\n".join(errors) if errors else "no candidates"
    raise CANError(
        "Unable to load CANFD vendor library. The system loader is tried by default; "
        "pass library_path=... or set "
        f"{_ENV_LIBRARY_PATH} to the libcanbus.so/HCanbus.dll path if the library is "
        f"not installed in a system search path. Attempted:\n{attempted}"
    )


def _preload_vendor_dependencies() -> None:
    if platform.system() != "Linux":
        return
    try:
        ctypes.CDLL(_LINUX_USB_LIBRARY_NAME, mode=ctypes.RTLD_GLOBAL)
    except OSError:
        return


def _library_candidates(library_path: str | Path | None) -> list[str | Path]:
    library_name = _default_library_name()
    candidates: list[str | Path] = []
    if library_path is not None:
        candidates.append(Path(library_path))
    env_path = os.environ.get(_ENV_LIBRARY_PATH)
    if env_path:
        candidates.append(Path(env_path))

    candidates.append(library_name)

    package_root = Path(__file__).resolve().parents[2]
    candidates.append(Path("/usr/local/lib") / library_name)
    candidates.append(package_root / "vendor" / "libcanbus" / library_name)
    candidates.append(package_root / "hand" / library_name)
    candidates.append(Path.cwd() / library_name)
    return candidates


def _default_library_name() -> str:
    return (
        _WINDOWS_LIBRARY_NAME if platform.system() == "Windows" else _LINUX_LIBRARY_NAME
    )


def _ctypes_loader() -> Any:
    if platform.system() == "Windows":
        return getattr(ctypes, "WinDLL")
    return ctypes.CDLL


def _bind_signatures(lib: Any) -> None:
    lib.CAN_ScanDevice.restype = ctypes.c_int
    lib.CAN_ScanDevice.argtypes = []

    lib.CAN_OpenDevice.restype = ctypes.c_int
    lib.CAN_OpenDevice.argtypes = [ctypes.c_uint, ctypes.c_uint]

    lib.CAN_CloseDevice.restype = ctypes.c_int
    lib.CAN_CloseDevice.argtypes = [ctypes.c_uint, ctypes.c_uint]

    lib.CAN_ReadDevInfo.restype = ctypes.c_int
    lib.CAN_ReadDevInfo.argtypes = [ctypes.c_uint, ctypes.POINTER(DevInfo)]

    lib.CANFD_Init.restype = ctypes.c_int
    lib.CANFD_Init.argtypes = [
        ctypes.c_uint,
        ctypes.c_uint,
        ctypes.POINTER(CanFDConfig),
    ]

    lib.CANFD_Transmit.restype = ctypes.c_int
    lib.CANFD_Transmit.argtypes = [
        ctypes.c_uint,
        ctypes.c_uint,
        ctypes.POINTER(CanFDMsg),
        ctypes.c_uint,
        ctypes.c_int,
    ]

    lib.CANFD_Receive.restype = ctypes.c_int
    lib.CANFD_Receive.argtypes = [
        ctypes.c_uint,
        ctypes.c_uint,
        ctypes.POINTER(CanFDMsg),
        ctypes.c_uint,
        ctypes.c_int,
    ]


def _decode_c_string(value: bytes) -> str:
    return bytes(value).split(_C_STRING_TERMINATOR, 1)[0].decode(errors="replace")
