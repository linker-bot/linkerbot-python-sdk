"""Unit tests for SocketCANFDBackend.

Subprocess invocations and python-can ``can.Bus`` are stubbed so these tests
run on any platform; a separate hardware-marked test (not included here) is
needed to exercise the real socketcan path against a vcan/real device.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any
from unittest import mock

import pytest

from linkerbot.comm.canfd import (
    CANFDBackend,
    CANFDMessage,
    SocketCANFDBackend,
)
from linkerbot.exceptions import CANError, ValidationError

pytestmark = [pytest.mark.canfd]


def _link_show_proc(
    *, returncode: int = 0, stdout: str = "[]", stderr: str = ""
) -> mock.Mock:
    proc = mock.Mock()
    proc.returncode = returncode
    proc.stdout = stdout
    proc.stderr = stderr
    return proc


def _link_show_payload(
    *,
    up: bool = True,
    fd: bool = True,
    bitrate: int = 1_000_000,
    data_bitrate: int = 5_000_000,
) -> str:
    return json.dumps(
        [
            {
                "flags": ["UP", "LOWER_UP"] if up else [],
                "linkinfo": {
                    "info_data": {
                        "ctrlmode": ["FD"] if fd else [],
                        "bittiming": {"bitrate": bitrate},
                        "data_bittiming": {"bitrate": data_bitrate},
                    }
                },
            }
        ]
    )


@pytest.fixture
def fake_can_bus():
    """Stub ``can.Bus`` so SocketCANFDBackend.__init__ does not open a real socket."""
    with mock.patch(
        "linkerbot.comm.canfd.socketcan_backend.can.Bus", autospec=True
    ) as bus_cls:
        instance = mock.MagicMock()
        bus_cls.return_value = instance
        yield instance


@pytest.fixture
def with_ip_present():
    with mock.patch(
        "linkerbot.comm.canfd.socketcan_backend.shutil.which",
        return_value="/usr/sbin/ip",
    ):
        yield


@pytest.fixture
def link_show(monkeypatch: pytest.MonkeyPatch) -> LinkShowFake:
    """Patch subprocess.run; default returns a 'link not configured' result."""
    fake_run = LinkShowFake()
    monkeypatch.setattr(
        "linkerbot.comm.canfd.socketcan_backend.subprocess.run", fake_run
    )
    return fake_run


@dataclass
class LinkShowFake:
    show_response: mock.Mock = field(
        default_factory=lambda: _link_show_proc(returncode=1)
    )
    set_response: mock.Mock = field(
        default_factory=lambda: _link_show_proc(returncode=0)
    )
    runs: list[list[str]] = field(default_factory=list)

    def __call__(self, args: list[str], **kwargs: Any) -> mock.Mock:
        _ = kwargs
        self.runs.append(list(args))
        if args[:3] == ["ip", "-d", "-j"]:
            return self.show_response
        return self.set_response


def test_socketcan_backend_satisfies_protocol(
    fake_can_bus, with_ip_present, link_show
) -> None:
    link_show.show_response = _link_show_proc(returncode=0, stdout=_link_show_payload())

    backend = SocketCANFDBackend(channel="can0")
    try:
        assert isinstance(backend, CANFDBackend)
    finally:
        backend.close()


def test_uses_existing_link_when_parameters_match(
    fake_can_bus, with_ip_present, link_show
) -> None:
    link_show.show_response = _link_show_proc(
        returncode=0,
        stdout=_link_show_payload(bitrate=1_000_000, data_bitrate=5_000_000, fd=True),
    )

    backend = SocketCANFDBackend(channel="can0")

    # Only the show invocation; no down/up should run
    set_invocations = [r for r in link_show.runs if r[1:3] != ["-d", "-j"]]
    assert set_invocations == []
    backend.close()


def test_matching_but_down_link_requires_bring_up(
    fake_can_bus, with_ip_present, link_show
) -> None:
    link_show.show_response = _link_show_proc(
        returncode=0,
        stdout=_link_show_payload(up=False),
    )

    with pytest.raises(CANError) as exc:
        SocketCANFDBackend(channel="can0")

    message = str(exc.value)
    assert "configured but down" in message
    assert "set can0 up" in message
    fake_can_bus.assert_not_called()


def test_auto_reconfigure_brings_up_matching_down_link_without_down_cycle(
    fake_can_bus, with_ip_present, link_show
) -> None:
    link_show.show_response = _link_show_proc(
        returncode=0,
        stdout=_link_show_payload(up=False),
    )

    backend = SocketCANFDBackend(channel="can0", auto_reconfigure=True)
    try:
        set_commands = [r for r in link_show.runs if r[1:3] != ["-d", "-j"]]
        assert len(set_commands) == 1
        assert "up" in set_commands[0]
        assert "down" not in set_commands[0]
    finally:
        backend.close()


def test_mismatch_raises_with_actionable_command(
    fake_can_bus, with_ip_present, link_show
) -> None:
    link_show.show_response = _link_show_proc(
        returncode=0,
        stdout=_link_show_payload(bitrate=500_000, data_bitrate=2_000_000),
    )

    with pytest.raises(CANError) as exc:
        SocketCANFDBackend(channel="can0")

    message = str(exc.value)
    assert "mismatch" in message
    assert "bitrate=500000" in message
    # Reconfigure path: must include 'down &&' because the link already exists.
    assert "set can0 down" in message
    assert "bitrate 1000000" in message
    assert "dbitrate 5000000" in message


def test_missing_link_command_does_not_include_down(
    fake_can_bus, with_ip_present, link_show
) -> None:
    """When the link does not exist yet, the suggested command must not start
    with 'ip link set <ch> down' — that step would fail with 'Cannot find
    device' and short-circuit the && chain."""
    link_show.show_response = _link_show_proc(returncode=1)

    with pytest.raises(CANError) as exc:
        SocketCANFDBackend(channel="can0")

    message = str(exc.value)
    assert "not configured" in message
    assert "set can0 up" in message
    assert "bitrate 1000000" in message
    # Crucially: no 'down' step in the suggested setup command.
    assert "down" not in message.split("Run:")[-1].splitlines()[1]


def test_missing_link_without_auto_reconfigure_raises(
    fake_can_bus, with_ip_present, link_show
) -> None:
    link_show.show_response = _link_show_proc(returncode=1)

    with pytest.raises(CANError, match="not configured"):
        SocketCANFDBackend(channel="can0")


def test_auto_reconfigure_brings_up_when_missing(
    fake_can_bus, with_ip_present, link_show
) -> None:
    link_show.show_response = _link_show_proc(returncode=1)

    backend = SocketCANFDBackend(channel="can0", auto_reconfigure=True)
    try:
        # Show + one set/up command (no down because the link does not exist)
        commands = [r for r in link_show.runs if r[:1] == ["ip"]]
        up_cmds = [c for c in commands if "up" in c]
        assert len(up_cmds) == 1
        assert up_cmds[0][:7] == [
            "ip",
            "link",
            "set",
            "can0",
            "up",
            "type",
            "can",
        ]
        assert "1000000" in up_cmds[0]
        assert "dbitrate" in up_cmds[0]
        assert "5000000" in up_cmds[0]
    finally:
        backend.close()


def test_auto_reconfigure_recycles_when_mismatched(
    fake_can_bus, with_ip_present, link_show
) -> None:
    link_show.show_response = _link_show_proc(
        returncode=0,
        stdout=_link_show_payload(bitrate=500_000, data_bitrate=2_000_000),
    )

    backend = SocketCANFDBackend(
        channel="can0",
        bitrate=1_000_000,
        data_bitrate=5_000_000,
        auto_reconfigure=True,
    )
    try:
        commands = [r for r in link_show.runs if r[:1] == ["ip"]]
        down_cmds = [c for c in commands if "down" in c]
        up_cmds = [c for c in commands if "up" in c]
        assert len(down_cmds) == 1
        assert len(up_cmds) == 1
    finally:
        backend.close()


def test_auto_reconfigure_failure_surfaces_ip_error(
    fake_can_bus, with_ip_present, link_show
) -> None:
    link_show.show_response = _link_show_proc(returncode=1)
    link_show.set_response = _link_show_proc(
        returncode=2, stdout="", stderr="Operation not permitted"
    )

    with pytest.raises(CANError, match="not permitted"):
        SocketCANFDBackend(channel="can0", auto_reconfigure=True)


def test_init_validates_arguments(fake_can_bus, with_ip_present, link_show) -> None:
    with pytest.raises(ValidationError):
        SocketCANFDBackend(channel="")
    with pytest.raises(ValidationError):
        SocketCANFDBackend(channel="can0", bitrate=0)
    with pytest.raises(ValidationError):
        SocketCANFDBackend(channel="can0", data_bitrate=-1)


def test_send_defaults_to_fd_without_bitrate_switch(
    fake_can_bus, with_ip_present, link_show
) -> None:
    link_show.show_response = _link_show_proc(returncode=0, stdout=_link_show_payload())
    backend = SocketCANFDBackend(channel="can0")

    payload = b"\x01\x02\x03\x04"
    backend.send(
        CANFDMessage(arbitration_id=0x123, data=payload, is_extended_id=False),
        timeout_ms=50,
    )

    sent = fake_can_bus.send.call_args
    msg = sent.args[0]
    assert msg.arbitration_id == 0x123
    assert msg.is_extended_id is False
    assert msg.is_fd is True
    assert msg.bitrate_switch is False
    assert bytes(msg.data) == payload
    assert sent.kwargs["timeout"] == pytest.approx(0.05)
    backend.close()


@pytest.mark.parametrize(
    ("frame_type", "expected_bitrate_switch"),
    [(0x04, False), (0x0C, True)],
)
def test_send_maps_vendor_frame_type_to_python_can_flags(
    fake_can_bus,
    with_ip_present,
    link_show,
    frame_type: int,
    expected_bitrate_switch: bool,
) -> None:
    link_show.show_response = _link_show_proc(returncode=0, stdout=_link_show_payload())
    backend = SocketCANFDBackend(channel="can0")

    backend.send(
        CANFDMessage(
            arbitration_id=0x123,
            data=b"\x01",
            frame_type=frame_type,
        )
    )

    sent = fake_can_bus.send.call_args.args[0]
    assert sent.is_fd is True
    assert sent.bitrate_switch is expected_bitrate_switch
    backend.close()


def test_send_pads_payload_to_explicit_raw_dlc(
    fake_can_bus, with_ip_present, link_show
) -> None:
    link_show.show_response = _link_show_proc(returncode=0, stdout=_link_show_payload())
    backend = SocketCANFDBackend(channel="can0")

    backend.send(CANFDMessage(arbitration_id=0x123, data=b"\x01\x02", dlc=9))

    sent = fake_can_bus.send.call_args.args[0]
    assert sent.dlc == 12
    assert bytes(sent.data) == b"\x01\x02" + bytes(10)
    backend.close()


def test_receive_translates_python_can_messages_back(
    fake_can_bus, with_ip_present, link_show
) -> None:
    link_show.show_response = _link_show_proc(returncode=0, stdout=_link_show_payload())
    incoming = mock.MagicMock()
    incoming.arbitration_id = 0x456
    incoming.is_extended_id = True
    incoming.is_fd = True
    incoming.bitrate_switch = False
    incoming.data = b"\xaa\xbb\xcc"
    pending = [incoming]

    def fake_recv(timeout: float):
        # Yield the queued frame on the first call, None on every subsequent
        # call so the receive loop can drain and return cleanly.
        if pending:
            return pending.pop(0)
        return None

    fake_can_bus.recv.side_effect = fake_recv

    backend = SocketCANFDBackend(channel="can0")
    try:
        frames = backend.receive(max_frames=4, timeout_ms=5)
    finally:
        backend.close()

    assert len(frames) == 1
    assert frames[0].arbitration_id == 0x456
    assert frames[0].is_extended_id is True
    assert frames[0].data == b"\xaa\xbb\xcc"
    assert frames[0].frame_type == 0x04


def test_receive_blocks_first_frame_then_drains_with_zero_timeout(
    fake_can_bus, with_ip_present, link_show
) -> None:
    """Performance contract: the first frame is awaited with one
    bus.recv(timeout=remaining) call; subsequent frames are drained with
    bus.recv(timeout=0). This avoids a 1ms poll loop that would burn
    syscalls and add per-frame latency."""
    link_show.show_response = _link_show_proc(returncode=0, stdout=_link_show_payload())

    timeouts_seen: list[float] = []
    msgs = [
        mock.MagicMock(arbitration_id=0x10 + i, is_extended_id=False, data=b"\x00")
        for i in range(2)
    ]

    def fake_recv(timeout):
        timeouts_seen.append(timeout)
        return msgs.pop(0) if msgs else None

    fake_can_bus.recv.side_effect = fake_recv

    backend = SocketCANFDBackend(channel="can0")
    try:
        frames = backend.receive(max_frames=4, timeout_ms=10)
    finally:
        backend.close()

    assert len(frames) == 2
    # First call: positive timeout (close to 10ms but bounded by jitter).
    assert timeouts_seen[0] > 0
    # Second + third calls: timeout=0 (drain phase, non-blocking).
    assert timeouts_seen[1:] == [0, 0]


def test_receive_returns_empty_when_no_frame_arrives_in_window(
    fake_can_bus, with_ip_present, link_show
) -> None:
    link_show.show_response = _link_show_proc(returncode=0, stdout=_link_show_payload())
    fake_can_bus.recv.return_value = None

    backend = SocketCANFDBackend(channel="can0")
    try:
        frames = backend.receive(max_frames=4, timeout_ms=2)
    finally:
        backend.close()

    assert frames == []
    # One call only, the kernel select handled the wait — not a busy poll.
    assert fake_can_bus.recv.call_count == 1


def test_receive_zero_timeout_performs_one_nonblocking_poll(
    fake_can_bus, with_ip_present, link_show
) -> None:
    link_show.show_response = _link_show_proc(returncode=0, stdout=_link_show_payload())
    incoming = mock.MagicMock(
        arbitration_id=0x456,
        is_extended_id=True,
        is_fd=True,
        bitrate_switch=False,
        data=b"\xaa",
    )
    fake_can_bus.recv.side_effect = [incoming, None]

    backend = SocketCANFDBackend(channel="can0")
    try:
        frames = backend.receive(max_frames=4, timeout_ms=0)
    finally:
        backend.close()

    assert [frame.data for frame in frames] == [b"\xaa"]
    assert fake_can_bus.recv.call_args_list[0] == mock.call(timeout=0.0)


def test_close_is_idempotent_and_blocks_further_io(
    fake_can_bus, with_ip_present, link_show
) -> None:
    link_show.show_response = _link_show_proc(returncode=0, stdout=_link_show_payload())
    backend = SocketCANFDBackend(channel="can0")

    backend.close()
    backend.close()
    fake_can_bus.shutdown.assert_called_once()

    with pytest.raises(CANError, match="closed"):
        backend.send(CANFDMessage(arbitration_id=0x1, data=b""))
    with pytest.raises(CANError, match="closed"):
        backend.receive()


def test_missing_ip_command_raises(fake_can_bus) -> None:
    with mock.patch(
        "linkerbot.comm.canfd.socketcan_backend.shutil.which", return_value=None
    ):
        with pytest.raises(CANError, match="iproute2"):
            SocketCANFDBackend(channel="can0")
