import ctypes
from pathlib import Path

import pytest

from linkerbot.comm.canfd import CANFDConfigOptions, CANFDMessage
from linkerbot.comm.canfd import ctypes_backend as backend
from linkerbot.exceptions import CANError, ValidationError


class FakeFunction:
    def __init__(self, result=0):
        self.result = result
        self.calls = []
        self.restype = None
        self.argtypes = None

    def __call__(self, *args):
        self.calls.append(args)
        return self.result


class FakeLibrary:
    def __init__(self) -> None:
        self.LibCANbus_Init = FakeFunction(0)
        self.LibCANbus_Exit = FakeFunction(0)
        self.CAN_ScanDevice = FakeFunction(1)
        self.CAN_OpenDevice = FakeFunction(0)
        self.CAN_CloseDevice = FakeFunction(0)
        self.CAN_ReadDevInfo = FakeFunction(0)
        self.CANFD_Init = FakeFunction(0)
        self.CANFD_Transmit = FakeFunction(1)
        self.CANFD_Receive = FakeFunction(0)


def make_interface(monkeypatch: pytest.MonkeyPatch, lib: FakeLibrary):
    monkeypatch.setattr(backend, "_load_library", lambda library_path: lib)
    return backend.CANFDInterface()


def test_ctypes_struct_fields() -> None:
    assert [name for name, _ in backend.CanFDConfig._fields_] == [
        "NomBaud",
        "DatBaud",
        "NomPre",
        "NomTseg1",
        "NomTseg2",
        "NomSJW",
        "DatPre",
        "DatTseg1",
        "DatTseg2",
        "DatSJW",
        "Config",
        "Model",
        "Cantype",
    ]
    assert [name for name, _ in backend.CanFDMsg._fields_][-1] == "Data"
    assert backend.CanFDMsg.Data.size == 64


def test_bind_signatures_sets_required_vendor_signatures() -> None:
    lib = FakeLibrary()

    backend._bind_signatures(lib)

    assert lib.CAN_ScanDevice.restype is ctypes.c_int
    assert lib.CAN_OpenDevice.argtypes == [ctypes.c_uint, ctypes.c_uint]
    assert lib.CANFD_Init.argtypes == [
        ctypes.c_uint,
        ctypes.c_uint,
        ctypes.POINTER(backend.CanFDConfig),
    ]
    assert lib.CANFD_Transmit.argtypes == [
        ctypes.c_uint,
        ctypes.c_uint,
        ctypes.POINTER(backend.CanFDMsg),
        ctypes.c_uint,
        ctypes.c_int,
    ]


def test_init_scans_opens_and_initializes(monkeypatch: pytest.MonkeyPatch) -> None:
    lib = FakeLibrary()

    interface = make_interface(monkeypatch, lib)

    assert interface.device_index == 0
    assert lib.CAN_ScanDevice.calls == [()]
    assert lib.CAN_OpenDevice.calls == [(0, 0)]
    assert len(lib.CANFD_Init.calls) == 1


def test_init_rejects_negative_device_index(monkeypatch: pytest.MonkeyPatch) -> None:
    lib = FakeLibrary()
    monkeypatch.setattr(backend, "_load_library", lambda library_path: lib)

    with pytest.raises(ValidationError):
        backend.CANFDInterface(device_index=-1)


def test_init_rejects_scan_error(monkeypatch: pytest.MonkeyPatch) -> None:
    lib = FakeLibrary()
    lib.CAN_ScanDevice.result = -1

    with pytest.raises(CANError, match="CAN_ScanDevice"):
        make_interface(monkeypatch, lib)


def test_init_rejects_no_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    lib = FakeLibrary()
    lib.CAN_ScanDevice.result = 0

    with pytest.raises(CANError, match="No CANFD adapter"):
        make_interface(monkeypatch, lib)


def test_init_rejects_device_index_out_of_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lib = FakeLibrary()

    monkeypatch.setattr(backend, "_load_library", lambda library_path: lib)
    with pytest.raises(CANError, match="out of range"):
        backend.CANFDInterface(device_index=1)


def test_init_open_failure_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    lib = FakeLibrary()
    lib.CAN_OpenDevice.result = 2

    with pytest.raises(CANError, match="CAN_OpenDevice"):
        make_interface(monkeypatch, lib)


def test_init_failure_closes_device(monkeypatch: pytest.MonkeyPatch) -> None:
    lib = FakeLibrary()
    lib.CANFD_Init.result = 3

    with pytest.raises(CANError, match="CANFD_Init"):
        make_interface(monkeypatch, lib)

    assert lib.CAN_CloseDevice.calls == [(0, 0)]


def test_send_translates_message_to_vendor_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lib = FakeLibrary()
    interface = make_interface(monkeypatch, lib)
    message = CANFDMessage(
        arbitration_id=0x123456,
        data=b"abc",
        is_extended_id=True,
        frame_type=0x04,
    )

    interface.send(message, timeout_ms=25)

    _, _, frame_ptr, count, timeout_ms = lib.CANFD_Transmit.calls[0]
    frame = frame_ptr._obj
    assert frame.ID == 0x123456
    assert frame.DLC == 3
    assert frame.FrameType == 0x04
    assert frame.ExternFlag == 1
    assert bytes(frame.Data[:3]) == b"abc"
    assert count == 1
    assert timeout_ms == 25


@pytest.mark.parametrize("status", [0, -1])
def test_send_failure_raises(monkeypatch: pytest.MonkeyPatch, status: int) -> None:
    lib = FakeLibrary()
    lib.CANFD_Transmit.result = status
    interface = make_interface(monkeypatch, lib)

    with pytest.raises(CANError, match="CANFD_Transmit"):
        interface.send(CANFDMessage(arbitration_id=1, data=b""))


def test_receive_timeout_returns_empty_list(monkeypatch: pytest.MonkeyPatch) -> None:
    lib = FakeLibrary()
    interface = make_interface(monkeypatch, lib)

    assert interface.receive() == []


def test_receive_negative_status_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    lib = FakeLibrary()
    lib.CANFD_Receive.result = -1
    interface = make_interface(monkeypatch, lib)

    with pytest.raises(CANError, match="CANFD_Receive"):
        interface.receive()


def test_receive_translates_vendor_frame(monkeypatch: pytest.MonkeyPatch) -> None:
    lib = FakeLibrary()

    def receive(dev, channel, buffer, max_frames, timeout_ms):
        frame = buffer[0]
        frame.ID = 0x123
        frame.TimeStamp = 456
        frame.FrameType = 0x0C
        frame.DLC = 9
        frame.ExternFlag = 1
        frame.Data[0] = 1
        frame.Data[11] = 12
        return 1

    lib.CANFD_Receive = FakeFunction()
    lib.CANFD_Receive.__call__ = receive

    class ReceiveFunction(FakeFunction):
        def __call__(self, dev, channel, buffer, max_frames, timeout_ms):
            return receive(dev, channel, buffer, max_frames, timeout_ms)

    lib.CANFD_Receive = ReceiveFunction()
    interface = make_interface(monkeypatch, lib)

    messages = interface.receive()

    assert messages == [
        CANFDMessage(
            arbitration_id=0x123,
            data=bytes([1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 12]),
            dlc=9,
            is_extended_id=True,
            frame_type=0x0C,
            timestamp=456,
        )
    ]


def test_read_dev_info_decodes_strings(monkeypatch: pytest.MonkeyPatch) -> None:
    lib = FakeLibrary()

    class ReadDevInfoFunction(FakeFunction):
        def __call__(self, dev, info_ptr):
            info = info_ptr._obj
            info.HW_Type = b"adapter"
            info.HW_Ser = b"serial"
            info.HW_Ver = b"hw"
            info.FW_Ver = b"fw"
            info.MF_Date = b"date"
            return 0

    lib.CAN_ReadDevInfo = ReadDevInfoFunction()
    interface = make_interface(monkeypatch, lib)

    assert interface.read_dev_info() == {
        "hw_type": "adapter",
        "hw_serial": "serial",
        "hw_version": "hw",
        "fw_version": "fw",
        "manufacture_date": "date",
    }


def test_library_candidates_prefer_explicit_env_then_system_loader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LINKERBOT_CANFD_LIB", "/env/libcanbus.so")

    candidates = backend._library_candidates(Path("/explicit/libcanbus.so"))

    assert candidates[0] == Path("/explicit/libcanbus.so")
    assert candidates[1] == Path("/env/libcanbus.so")
    assert candidates[2] == backend._default_library_name()


def test_library_candidates_default_to_system_loader() -> None:
    candidates = backend._library_candidates(None)

    assert candidates[0] == backend._default_library_name()
    assert any(str(candidate).endswith("hand/libcanbus.so") for candidate in candidates)


def test_load_library_error_mentions_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingLoader:
        def __call__(self, path: str):
            raise OSError("missing")

    monkeypatch.setattr(backend, "_ctypes_loader", lambda: FailingLoader())
    monkeypatch.setattr(
        backend, "_library_candidates", lambda library_path: ["missing.so"]
    )

    with pytest.raises(CANError, match="LINKERBOT_CANFD_LIB"):
        backend._load_library(None)


def test_close_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    lib = FakeLibrary()
    interface = make_interface(monkeypatch, lib)

    interface.close()
    interface.close()

    assert lib.CAN_CloseDevice.calls == [(0, 0)]


def test_close_failure_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    lib = FakeLibrary()
    lib.CAN_CloseDevice.result = 1
    interface = make_interface(monkeypatch, lib)

    with pytest.raises(CANError, match="CAN_CloseDevice"):
        interface.close()


def test_default_config_maps_to_vendor_struct(monkeypatch: pytest.MonkeyPatch) -> None:
    lib = FakeLibrary()

    make_interface(monkeypatch, lib)

    config = lib.CANFD_Init.calls[0][2]._obj
    assert config.NomBaud == 1_000_000
    assert config.DatBaud == 5_000_000
    assert config.Config == 0x07
    assert config.Model == 0
    assert config.Cantype == 1


def test_custom_config_maps_to_vendor_struct(monkeypatch: pytest.MonkeyPatch) -> None:
    lib = FakeLibrary()
    monkeypatch.setattr(backend, "_load_library", lambda library_path: lib)

    backend.CANFDInterface(config=CANFDConfigOptions(frame_type=0x04, config=0x01))

    config = lib.CANFD_Init.calls[0][2]._obj
    assert config.Config == 0x01
