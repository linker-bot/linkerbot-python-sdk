"""Linux SocketCAN FD backend for ``CANFDMessageDispatcher``.

Wraps python-can's ``socketcan`` interface in CAN FD mode. Unlike the ctypes
backend (vendor ``libcanbus.so`` / ``HCanbus.dll``) which configures the
adapter bitrate from the SDK at open time, SocketCAN's bitrate lives at the
kernel level and is configured once via ``ip link``. Multiple processes share
the same ``can0`` link, so this backend treats the link as observed shared
state rather than something it owns:

- If ``<channel>`` is already up with matching ``bitrate`` /
  ``data_bitrate`` / ``fd``, the backend uses it as-is.
- If ``<channel>`` is up with mismatched parameters, the backend raises
  :class:`CANError` showing the exact ``ip link`` command needed to fix it,
  unless ``auto_reconfigure=True`` is passed.
- If ``<channel>`` is not configured, the backend either runs ``ip link``
  itself (``auto_reconfigure=True``) or raises :class:`CANError` with the
  exact command for the user to run manually.

``auto_reconfigure`` defaults to ``False`` because the operations it would run
(``ip link set ... down`` / ``up``) require ``CAP_NET_ADMIN`` and side-affect
any other process currently using the link.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import threading
import time

import can

from linkerbot.exceptions import CANError, ValidationError

from .types import (
    CANFD_DEFAULT_DATA_BAUD,
    CANFD_DEFAULT_NOMINAL_BAUD,
    CANFDMessage,
    dlc_to_length,
    length_to_dlc,
)

DEFAULT_NOMINAL_BITRATE = CANFD_DEFAULT_NOMINAL_BAUD
DEFAULT_DATA_BITRATE = CANFD_DEFAULT_DATA_BAUD
# Vendor FrameType uses bit 2 for CAN FD and bit 3 for bit-rate switching.
# These flags map directly to python-can's is_fd / bitrate_switch fields.
_FRAME_TYPE_FD = 0x04
_FRAME_TYPE_BRS = 0x08


class _LinkState:
    """Decoded SocketCAN link state from ``ip -d -j link show``."""

    __slots__ = ("up", "fd", "bitrate", "data_bitrate")

    def __init__(
        self,
        *,
        up: bool,
        fd: bool,
        bitrate: int | None,
        data_bitrate: int | None,
    ) -> None:
        self.up = up
        self.fd = fd
        self.bitrate = bitrate
        self.data_bitrate = data_bitrate

    def matches(self, *, bitrate: int, data_bitrate: int, fd: bool) -> bool:
        if self.fd != fd:
            return False
        if self.bitrate != bitrate:
            return False
        if fd and self.data_bitrate != data_bitrate:
            return False
        return True


class SocketCANFDBackend:
    """Linux SocketCAN backend in CAN FD mode.

    Implements :class:`linkerbot.comm.canfd.CANFDBackend`. Construct one of
    these and pass it to :class:`CANFDMessageDispatcher` via ``interface=`` to
    use SocketCAN instead of the vendor ctypes backend.
    """

    def __init__(
        self,
        channel: str,
        *,
        bitrate: int = DEFAULT_NOMINAL_BITRATE,
        data_bitrate: int = DEFAULT_DATA_BITRATE,
        fd: bool = True,
        auto_reconfigure: bool = False,
        receive_own_messages: bool = False,
    ) -> None:
        """Open a SocketCAN FD link.

        Args:
            channel: SocketCAN interface name (for example ``"can0"``).
            bitrate: Nominal (arbitration) bitrate in bits/sec.
                Defaults to 1 Mbit/s.
            data_bitrate: Data-phase bitrate in bits/sec when ``fd=True``.
                Defaults to 5 Mbit/s.
            fd: Whether to enable CAN FD framing. Set to False for plain
                CAN 2.0 over the same backend.
            auto_reconfigure: When True, the backend will run ``ip link``
                itself if the link is missing or has mismatched parameters.
                Requires ``CAP_NET_ADMIN`` (typically root). Default False.
            receive_own_messages: Forwarded to ``can.Bus``; whether the bus
                echoes locally-sent frames back through ``recv()``.

        Raises:
            ValidationError: If the channel name or bitrates are invalid.
            CANError: If ``ip`` is missing, the link is misconfigured and
                ``auto_reconfigure`` is False, or ``ip link`` itself fails.
        """
        if not isinstance(channel, str) or not channel:
            raise ValidationError("channel must be a non-empty string (e.g. 'can0')")
        if not isinstance(bitrate, int) or bitrate <= 0:
            raise ValidationError("bitrate must be a positive int")
        if not isinstance(data_bitrate, int) or data_bitrate <= 0:
            raise ValidationError("data_bitrate must be a positive int")

        self._channel = channel
        self._bitrate = bitrate
        self._data_bitrate = data_bitrate
        self._fd = bool(fd)
        self._lock = threading.Lock()
        self._closed = False

        self._ensure_link_state(auto_reconfigure=auto_reconfigure)

        self._bus = can.Bus(
            channel=channel,
            interface="socketcan",
            fd=self._fd,
            receive_own_messages=receive_own_messages,
        )

    @property
    def channel(self) -> str:
        """SocketCAN interface name this backend is bound to."""
        return self._channel

    @property
    def bitrate(self) -> int:
        """Nominal (arbitration) bitrate in bits/sec."""
        return self._bitrate

    @property
    def data_bitrate(self) -> int:
        """Data-phase bitrate in bits/sec; equal to ``bitrate`` if ``fd`` is False."""
        return self._data_bitrate

    @property
    def fd(self) -> bool:
        """Whether CAN FD framing is enabled."""
        return self._fd

    def send(self, message: CANFDMessage, timeout_ms: int = 10) -> None:
        """Transmit a single CAN FD frame.

        Args:
            message: Frame to send.
            timeout_ms: Maximum time to block waiting for the transmit slot.

        Raises:
            CANError: If the backend is closed or python-can returns an error.
        """
        if timeout_ms < 0:
            raise ValidationError("timeout_ms must be non-negative")
        if self._closed:
            raise CANError("SocketCAN FD backend is closed")

        is_fd, bitrate_switch = self._frame_flags(message)
        dlc = (
            message.dlc if message.dlc is not None else length_to_dlc(len(message.data))
        )
        if is_fd:
            wire_length = dlc_to_length(dlc)
        else:
            if dlc > 8:
                raise ValidationError(
                    "classic CAN frames cannot use a DLC greater than 8"
                )
            wire_length = dlc

        # python-can models CAN FD ``dlc`` as the payload byte count, whereas
        # CANFDMessage stores the encoded 0..15 DLC. Pad to the encoded DLC's
        # wire capacity so explicit DLC overrides behave exactly like the
        # vendor ctypes backend (whose pre-zeroed 64-byte buffer is sent with
        # the requested raw DLC).
        data = message.data.ljust(wire_length, b"\x00")
        try:
            self._bus.send(
                can.Message(
                    arbitration_id=message.arbitration_id,
                    is_extended_id=message.is_extended_id,
                    is_fd=is_fd,
                    bitrate_switch=bitrate_switch,
                    data=data,
                    check=True,
                ),
                timeout=timeout_ms / 1000.0,
            )
        except can.CanError as error:
            raise CANError(f"SocketCAN FD send failed: {error}") from error

    def _frame_flags(self, message: CANFDMessage) -> tuple[bool, bool]:
        """Resolve vendor FrameType bits to python-can frame flags."""
        if message.frame_type is None:
            return self._fd, self._fd

        is_fd = bool(message.frame_type & _FRAME_TYPE_FD)
        bitrate_switch = bool(message.frame_type & _FRAME_TYPE_BRS)
        if bitrate_switch and not is_fd:
            raise ValidationError("FrameType BRS bit requires the CAN FD bit")
        if is_fd and not self._fd:
            raise ValidationError(
                "CAN FD message cannot be sent when the SocketCAN backend has fd=False"
            )
        return is_fd, bitrate_switch

    def receive(self, max_frames: int = 64, timeout_ms: int = 10) -> list[CANFDMessage]:
        """Receive up to ``max_frames`` frames within ``timeout_ms``.

        The first frame is awaited via a single ``bus.recv(timeout=remaining)``
        call so the kernel can block on its socket efficiently. Once any frame
        arrives, the remaining slots are drained with ``timeout=0`` (non-
        blocking) until either ``max_frames`` is reached or the kernel buffer
        is empty. Returns an empty list when nothing arrives in time.
        """
        if self._closed:
            raise CANError("SocketCAN FD backend is closed")
        if max_frames <= 0:
            raise ValidationError("max_frames must be positive")
        if timeout_ms < 0:
            raise ValidationError("timeout_ms must be non-negative")

        deadline = time.monotonic() + timeout_ms / 1000.0
        result: list[CANFDMessage] = []

        # First frame: block up to the full remaining timeout in a single
        # recv() so the kernel can park us on its socket; no busy poll.
        while not result:
            remaining = deadline - time.monotonic()
            if remaining < 0:
                return result
            try:
                msg = self._bus.recv(timeout=remaining)
            except can.CanError as error:
                raise CANError(f"SocketCAN FD receive failed: {error}") from error
            if msg is None:
                return result
            result.append(_to_canfd_message(msg))

        # Drain any frames already in the kernel buffer; stop as soon as the
        # buffer is empty (timeout=0) or we hit max_frames.
        while len(result) < max_frames:
            try:
                msg = self._bus.recv(timeout=0)
            except can.CanError as error:
                raise CANError(f"SocketCAN FD receive failed: {error}") from error
            if msg is None:
                break
            result.append(_to_canfd_message(msg))
        return result

    def close(self) -> None:
        """Shutdown the python-can bus. Idempotent.

        This does not run ``ip link set ... down`` — the link is shared state
        and may be in use by other processes.
        """
        with self._lock:
            if self._closed:
                return
            self._closed = True
            try:
                self._bus.shutdown()
            except Exception:
                pass

    def _ensure_link_state(self, *, auto_reconfigure: bool) -> None:
        state = _read_link_state(self._channel)
        if state is None:
            if auto_reconfigure:
                _bring_up(self._channel, self._bitrate, self._data_bitrate, self._fd)
                return
            setup_cmd = _format_setup_command(
                self._channel, self._bitrate, self._data_bitrate, self._fd
            )
            raise CANError(
                f"SocketCAN channel {self._channel!r} is not configured. Run:\n"
                f"  {setup_cmd}\n"
                f"or pass auto_reconfigure=True (requires CAP_NET_ADMIN)."
            )
        if state.matches(
            bitrate=self._bitrate, data_bitrate=self._data_bitrate, fd=self._fd
        ):
            if state.up:
                return
            if auto_reconfigure:
                _bring_up(self._channel, self._bitrate, self._data_bitrate, self._fd)
                return
            setup_cmd = _format_setup_command(
                self._channel, self._bitrate, self._data_bitrate, self._fd
            )
            raise CANError(
                f"SocketCAN channel {self._channel!r} is configured but down. Run:\n"
                f"  {setup_cmd}\n"
                f"or pass auto_reconfigure=True."
            )
        if auto_reconfigure:
            if state.up:
                _bring_down(self._channel)
            _bring_up(self._channel, self._bitrate, self._data_bitrate, self._fd)
            return
        if state.up:
            reconfigure_cmd = _format_reconfigure_command(
                self._channel, self._bitrate, self._data_bitrate, self._fd
            )
        else:
            reconfigure_cmd = _format_setup_command(
                self._channel, self._bitrate, self._data_bitrate, self._fd
            )
        state_name = "up" if state.up else "down"
        raise CANError(
            f"SocketCAN channel {self._channel!r} is {state_name} but parameters mismatch. "
            f"Current: bitrate={state.bitrate}, data_bitrate={state.data_bitrate}, "
            f"fd={state.fd}. Wanted: bitrate={self._bitrate}, "
            f"data_bitrate={self._data_bitrate}, fd={self._fd}.\n"
            f"Run:\n  {reconfigure_cmd}\n"
            f"or pass auto_reconfigure=True."
        )


def _to_canfd_message(msg: can.Message) -> CANFDMessage:
    """Convert a python-can ``Message`` into our ``CANFDMessage``."""
    data = bytes(msg.data)
    frame_type = 0
    if msg.is_fd:
        frame_type |= _FRAME_TYPE_FD
    if msg.bitrate_switch:
        frame_type |= _FRAME_TYPE_BRS
    return CANFDMessage(
        arbitration_id=msg.arbitration_id,
        data=data,
        dlc=length_to_dlc(len(data)),
        is_extended_id=msg.is_extended_id,
        frame_type=frame_type,
    )


def _format_setup_command(
    channel: str, bitrate: int, data_bitrate: int, fd: bool
) -> str:
    """``ip link`` command to bring up a link that does not exist yet."""
    parts = [
        "sudo ip link set",
        channel,
        "up type can",
        f"bitrate {bitrate}",
    ]
    if fd:
        parts.append(f"dbitrate {data_bitrate} fd on")
    return " ".join(parts)


def _format_reconfigure_command(
    channel: str, bitrate: int, data_bitrate: int, fd: bool
) -> str:
    """``ip link`` command to reconfigure a link that is already up."""
    return f"sudo ip link set {channel} down && " + _format_setup_command(
        channel, bitrate, data_bitrate, fd
    )


def _read_link_state(channel: str) -> _LinkState | None:
    """Return the parsed link state, or None if the link does not exist."""
    if shutil.which("ip") is None:
        raise CANError(
            "'ip' command not found; SocketCAN backend requires Linux with iproute2"
        )
    proc = subprocess.run(
        ["ip", "-d", "-j", "link", "show", channel],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return None
    try:
        data = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError as error:
        raise CANError(
            f"failed to parse 'ip -d -j link show {channel}' output: {error}"
        ) from error
    if not data:
        return None
    entry = data[0]
    flags = entry.get("flags", []) or []
    up = "UP" in flags
    linkinfo = entry.get("linkinfo") or {}
    info_data = linkinfo.get("info_data") or {}
    bittiming = info_data.get("bittiming") or {}
    data_bittiming = info_data.get("data_bittiming") or {}
    ctrlmode = info_data.get("ctrlmode") or []
    fd = "FD" in ctrlmode
    return _LinkState(
        up=up,
        fd=fd,
        bitrate=bittiming.get("bitrate"),
        data_bitrate=data_bittiming.get("bitrate"),
    )


def _bring_down(channel: str) -> None:
    _run_ip(["link", "set", channel, "down"])


def _bring_up(channel: str, bitrate: int, data_bitrate: int, fd: bool) -> None:
    args = ["link", "set", channel, "up", "type", "can", "bitrate", str(bitrate)]
    if fd:
        args += ["dbitrate", str(data_bitrate), "fd", "on"]
    _run_ip(args)


def _run_ip(args: list[str]) -> None:
    proc = subprocess.run(
        ["ip", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        msg = proc.stderr.strip() or proc.stdout.strip() or "no output"
        raise CANError(
            f"'ip {' '.join(args)}' failed (rc={proc.returncode}): {msg}. "
            "auto_reconfigure requires CAP_NET_ADMIN; run as root or grant capability."
        )
