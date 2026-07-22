import ctypes
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from linkerbot.comm.canfd import CANFDConfigOptions, CANFDMessage
from linkerbot.comm.canfd import ctypes_backend as backend
from linkerbot.exceptions import CANError, ValidationError


class FakeFunction:
    def __init__(
        self,
        result: int = 0,
        hook: Callable[..., int] | None = None,
    ) -> None:
        self.result = result
        self.hook = hook
        self.calls: list[tuple[Any, ...]] = []
        self.restype: Any = None
        self.argtypes: list[Any] | None = None

    def __call__(self, *args: Any) -> int:
        self.calls.append(args)
        if self.hook is not None:
            return self.hook(*args)
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


def make_interface(
    monkeypatch: pytest.MonkeyPatch, lib: FakeLibrary
) -> backend.CANFDInterface:
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


@pytest.mark.parametrize("status", [0, -1, 2])
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


def test_receive_rejects_vendor_count_above_requested_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lib = FakeLibrary()
    lib.CANFD_Receive.result = 2
    interface = make_interface(monkeypatch, lib)

    with pytest.raises(CANError, match="more frames than requested"):
        interface.receive(max_frames=1)


def test_receive_translates_vendor_frame(monkeypatch: pytest.MonkeyPatch) -> None:
    lib = FakeLibrary()

    def receive(
        dev: Any, channel: Any, buffer: Any, max_frames: Any, timeout_ms: Any
    ) -> int:
        _ = dev, channel, max_frames, timeout_ms
        frame = buffer[0]
        frame.ID = 0x123
        frame.TimeStamp = 456
        frame.FrameType = 0x0C
        frame.DLC = 9
        frame.ExternFlag = 1
        frame.Data[0] = 1
        frame.Data[11] = 12
        return 1

    lib.CANFD_Receive = FakeFunction(hook=receive)
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

    def read_dev_info(dev: Any, info_ptr: Any) -> int:
        _ = dev
        info = info_ptr._obj
        info.HW_Type = b"adapter"
        info.HW_Ser = b"serial"
        info.HW_Ver = b"hw"
        info.FW_Ver = b"fw"
        info.MF_Date = b"date"
        return 0

    lib.CAN_ReadDevInfo = FakeFunction(hook=read_dev_info)
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


def test_concurrent_close_waits_for_io_device_close_and_lifecycle_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lib = FakeLibrary()
    send_entered = threading.Event()
    receive_entered = threading.Event()
    vendor_close_entered = threading.Event()
    lifecycle_exit_entered = threading.Event()
    allow_send = threading.Event()
    allow_receive = threading.Event()
    allow_vendor_close = threading.Event()
    allow_lifecycle_exit = threading.Event()

    def blocking_send(*args: Any) -> int:
        _ = args
        send_entered.set()
        if not allow_send.wait(timeout=2.0):
            raise TimeoutError("test did not release CANFD_Transmit")
        return 1

    def blocking_receive(*args: Any) -> int:
        _ = args
        receive_entered.set()
        if not allow_receive.wait(timeout=2.0):
            raise TimeoutError("test did not release CANFD_Receive")
        return 0

    def blocking_vendor_close(*args: Any) -> int:
        _ = args
        vendor_close_entered.set()
        if not allow_vendor_close.wait(timeout=2.0):
            raise TimeoutError("test did not release CAN_CloseDevice")
        return 0

    def blocking_lifecycle_exit(*args: Any) -> int:
        _ = args
        lifecycle_exit_entered.set()
        if not allow_lifecycle_exit.wait(timeout=2.0):
            raise TimeoutError("test did not release LibCANbus_Exit")
        return 0

    lib.CANFD_Transmit.hook = blocking_send
    lib.CANFD_Receive.hook = blocking_receive
    lib.CAN_CloseDevice.hook = blocking_vendor_close
    lib.LibCANbus_Exit.hook = blocking_lifecycle_exit
    interface = make_interface(monkeypatch, lib)

    errors: list[Exception] = []
    send_done = threading.Event()
    receive_done = threading.Event()
    first_close_done = threading.Event()
    second_close_done = threading.Event()

    def run(operation: Callable[[], object], done: threading.Event) -> None:
        try:
            operation()
        except Exception as error:
            errors.append(error)
        finally:
            done.set()

    message = CANFDMessage(arbitration_id=1, data=b"x")
    send_thread = threading.Thread(
        target=run,
        args=(lambda: interface.send(message), send_done),
        daemon=True,
    )
    receive_thread = threading.Thread(
        target=run,
        args=(interface.receive, receive_done),
        daemon=True,
    )
    send_thread.start()
    receive_thread.start()
    assert send_entered.wait(timeout=1.0)
    assert receive_entered.wait(timeout=1.0)

    first_close_thread = threading.Thread(
        target=run,
        args=(interface.close, first_close_done),
        daemon=True,
    )
    first_close_thread.start()
    assert interface._closed_event.wait(timeout=1.0)

    second_close_thread = threading.Thread(
        target=run,
        args=(interface.close, second_close_done),
        daemon=True,
    )
    second_close_thread.start()
    assert not second_close_done.wait(timeout=0.05)

    # The owner drains transmit before receive, and neither close caller may
    # return while either in-flight vendor call still owns its direction lock.
    allow_send.set()
    assert send_done.wait(timeout=1.0)
    assert not vendor_close_entered.wait(timeout=0.05)
    assert not second_close_done.is_set()

    allow_receive.set()
    assert receive_done.wait(timeout=1.0)
    assert vendor_close_entered.wait(timeout=1.0)
    assert not first_close_done.is_set()
    assert not second_close_done.is_set()

    # Device close alone is not completion: the process-level lifecycle exit
    # must finish before a waiter can safely return and reopen the library.
    allow_vendor_close.set()
    assert lifecycle_exit_entered.wait(timeout=1.0)
    assert not first_close_done.is_set()
    assert not second_close_done.is_set()

    allow_lifecycle_exit.set()
    assert first_close_done.wait(timeout=1.0)
    assert second_close_done.wait(timeout=1.0)
    for thread in (
        send_thread,
        receive_thread,
        first_close_thread,
        second_close_thread,
    ):
        thread.join(timeout=1.0)
        assert not thread.is_alive()

    assert errors == []
    assert lib.CAN_CloseDevice.calls == [(0, 0)]
    assert len(lib.LibCANbus_Init.calls) == 1
    assert len(lib.LibCANbus_Exit.calls) == 1

    reopened = backend.CANFDInterface()
    assert len(lib.LibCANbus_Init.calls) == 2
    reopened.close()
    assert len(lib.CAN_CloseDevice.calls) == 2
    assert len(lib.LibCANbus_Exit.calls) == 2


def test_concurrent_close_waiter_is_notified_when_vendor_close_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lib = FakeLibrary()
    vendor_close_entered = threading.Event()
    allow_vendor_close = threading.Event()

    def failing_vendor_close(*args: Any) -> int:
        _ = args
        vendor_close_entered.set()
        if not allow_vendor_close.wait(timeout=2.0):
            raise TimeoutError("test did not release CAN_CloseDevice")
        raise OSError("vendor close crashed")

    lib.CAN_CloseDevice.hook = failing_vendor_close
    interface = make_interface(monkeypatch, lib)
    first_errors: list[Exception] = []
    second_errors: list[Exception] = []
    first_done = threading.Event()
    second_done = threading.Event()

    def call_close(errors: list[Exception], done: threading.Event) -> None:
        try:
            interface.close()
        except Exception as error:
            errors.append(error)
        finally:
            done.set()

    first_thread = threading.Thread(
        target=call_close,
        args=(first_errors, first_done),
        daemon=True,
    )
    first_thread.start()
    assert vendor_close_entered.wait(timeout=1.0)

    second_thread = threading.Thread(
        target=call_close,
        args=(second_errors, second_done),
        daemon=True,
    )
    second_thread.start()
    assert not second_done.wait(timeout=0.05)

    allow_vendor_close.set()
    assert first_done.wait(timeout=1.0)
    assert second_done.wait(timeout=1.0)
    first_thread.join(timeout=1.0)
    second_thread.join(timeout=1.0)

    assert len(first_errors) == 1
    assert isinstance(first_errors[0], CANError)
    assert "vendor close crashed" in str(first_errors[0])
    assert second_errors == []
    assert lib.CAN_CloseDevice.calls == [(0, 0)]
    assert len(lib.LibCANbus_Exit.calls) == 1
    assert interface._close_complete_event.is_set()


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
