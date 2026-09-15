"""Regression tests for responses delivered synchronously from ``send()``."""

from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, cast

import can
import pytest

from linkerbot.exceptions import TimeoutError
from linkerbot.hand.l6.angle import AngleManager as L6AngleManager
from linkerbot.hand.l6.version import VersionManager as L6VersionManager
from linkerbot.hand.l20lite.angle import AngleManager as L20LiteAngleManager
from linkerbot.hand.l25.angle import AngleManager as L25AngleManager
from linkerbot.hand.o6.angle import AngleManager as O6AngleManager
from linkerbot.hand.o6.fault import FaultManager as O6FaultManager

ResponseFactory = Callable[[can.Message], tuple[can.Message, ...]]


class _SynchronousDispatcher:
    """Deliver generated responses before ``send()`` returns."""

    def __init__(self, responses: ResponseFactory) -> None:
        self._responses = responses
        self._callbacks: list[Callable[[can.Message], None]] = []
        self.sent: list[can.Message] = []

    def subscribe(self, callback: Callable[[can.Message], None]) -> None:
        self._callbacks.append(callback)

    def send(self, msg: can.Message) -> None:
        self.sent.append(msg)
        for response in self._responses(msg):
            for callback in tuple(self._callbacks):
                callback(response)


def _response(request: can.Message, data: list[int]) -> can.Message:
    return can.Message(
        arbitration_id=request.arbitration_id,
        data=data,
        is_extended_id=False,
    )


@pytest.mark.parametrize(
    "manager_type,frame_sizes,joint_count",
    (
        (L6AngleManager, {0x01: 6}, 6),
        (O6AngleManager, {0x01: 6}, 6),
        (L20LiteAngleManager, {0x01: 6, 0x04: 4}, 10),
        (L25AngleManager, {cmd: 6 for cmd in range(0x41, 0x46)}, 16),
    ),
)
def test_classic_angle_managers_capture_synchronous_responses(
    tmp_path: Path,
    manager_type: type[Any],
    frame_sizes: dict[int, int],
    joint_count: int,
) -> None:
    def responses(request: can.Message) -> tuple[can.Message, ...]:
        command = int(request.data[0])
        return (_response(request, [command, *([128] * frame_sizes[command])]),)

    dispatcher = _SynchronousDispatcher(responses)
    manager = manager_type(
        0x28,
        dispatcher,
        angle_mapping_path=tmp_path / f"{manager_type.__module__}.toml",
    )

    data = manager.get_blocking(timeout_ms=20)

    assert len(data.angles.to_list()) == joint_count
    assert data.angles.to_list() == pytest.approx([128 * 100 / 255] * joint_count)
    assert [int(message.data[0]) for message in dispatcher.sent] == list(frame_sizes)


def test_fault_manager_captures_synchronous_response() -> None:
    dispatcher = _SynchronousDispatcher(
        lambda request: (_response(request, [0x35, 0, 0, 0, 0, 0, 0]),)
    )
    manager = O6FaultManager(0x28, cast(Any, dispatcher))

    data = manager.get_blocking(timeout_ms=20)

    assert not data.faults.has_any_fault()


def test_version_manager_captures_all_synchronous_responses() -> None:
    serial_fragments = (
        (0, b"ABCDEF"),
        (1, b"GHIJKL"),
        (2, b"MNOPQR"),
        (3, b"ST\0\0\0\0"),
    )

    def responses(request: can.Message) -> tuple[can.Message, ...]:
        command = int(request.data[0])
        if command == 0xC0:
            return tuple(
                _response(request, [command, position, *payload])
                for position, payload in serial_fragments
            )
        if command == 0xC1:
            return (_response(request, [command, 0x01, 7, 8, 9]),)
        if command == 0xC2:
            return (_response(request, [command, 1, 2, 3]),)
        if command == 0xC4:
            return (_response(request, [command, 4, 5, 6]),)
        raise AssertionError(f"unexpected version command: {command:#x}")

    manager = L6VersionManager(0x28, cast(Any, _SynchronousDispatcher(responses)))

    info = manager.get_device_info()

    assert info.serial_number == "ABCDEFGHIJKLMNOPQRST"
    assert (info.firmware_version.major, info.firmware_version.minor) == (1, 2)
    assert (info.mechanical_version.major, info.mechanical_version.minor) == (4, 5)
    assert (info.pcb_version.major, info.pcb_version.minor) == (7, 8)


def test_manager_recovers_after_synchronous_send_error(tmp_path: Path) -> None:
    error = RuntimeError("send failed")
    attempts = 0

    def responses(request: can.Message) -> tuple[can.Message, ...]:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise error
        return (_response(request, [0x01, 1, 2, 3, 4, 5, 6]),)

    manager = L6AngleManager(
        0x28,
        _SynchronousDispatcher(responses),
        angle_mapping_path=tmp_path / "l6.toml",
    )

    with pytest.raises(RuntimeError) as raised:
        manager.get_blocking(timeout_ms=20)
    assert raised.value is error

    assert len(manager.get_blocking(timeout_ms=20).angles.to_list()) == 6


def test_manager_recovers_after_timeout(tmp_path: Path) -> None:
    attempts = 0

    def responses(request: can.Message) -> tuple[can.Message, ...]:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return ()
        return (_response(request, [0x01, 1, 2, 3, 4, 5, 6]),)

    manager = L6AngleManager(
        0x28,
        _SynchronousDispatcher(responses),
        angle_mapping_path=tmp_path / "l6.toml",
    )

    with pytest.raises(TimeoutError, match="within 1ms"):
        manager.get_blocking(timeout_ms=1)

    assert len(manager.get_blocking(timeout_ms=20).angles.to_list()) == 6


def test_multiframe_manager_serializes_concurrent_blocking_requests(
    tmp_path: Path,
) -> None:
    first_send_started = threading.Event()
    release_first_send = threading.Event()
    blocked_once = False

    def responses(request: can.Message) -> tuple[can.Message, ...]:
        nonlocal blocked_once
        command = int(request.data[0])
        if command == 0x01 and not blocked_once:
            blocked_once = True
            first_send_started.set()
            assert release_first_send.wait(1.0)
        frame_size = 6 if command == 0x01 else 4
        return (_response(request, [command, *([128] * frame_size)]),)

    dispatcher = _SynchronousDispatcher(responses)
    manager = L20LiteAngleManager(
        0x28,
        dispatcher,
        angle_mapping_path=tmp_path / "l20lite.toml",
    )
    second_started = threading.Event()

    def second_request() -> Any:
        second_started.set()
        return manager.get_blocking(timeout_ms=500)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(manager.get_blocking, 500)
        assert first_send_started.wait(1.0)
        second = executor.submit(second_request)
        assert second_started.wait(1.0)
        assert [int(message.data[0]) for message in dispatcher.sent] == [0x01]

        release_first_send.set()
        first_result = first.result(timeout=1.0)
        second_result = second.result(timeout=1.0)

    assert first_result.angles.to_list() == pytest.approx([128 * 100 / 255] * 10)
    assert second_result.angles.to_list() == pytest.approx([128 * 100 / 255] * 10)
    assert [int(message.data[0]) for message in dispatcher.sent] == [
        0x01,
        0x04,
        0x01,
        0x04,
    ]
