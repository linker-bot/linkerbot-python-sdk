"""O20 robotic hand control interface.

This module provides the main O20 class for controlling the O20 CANFD robotic
hand. It integrates register read/write commands, blocking sensor reads,
host-side polling, and unified event streaming into a single SDK entry point.
"""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from linkerbot.comm.canfd import (
    CANFDConfigOptions,
    CANFDMessageDispatcher,
    SocketCANFDBackend,
)
from linkerbot.exceptions import CANError, LinkerbotError, StateError, ValidationError
from linkerbot.queue import IterableQueue

from . import protocol
from .angle import AngleManager
from .client import O20Client, O20DispatcherLike
from .current import CurrentManager
from .events import (
    AngleEvent,
    CurrentEvent,
    FaultEvent,
    ForceSensorEvent,
    O20Snapshot,
    SensorEvent,
    SensorSource,
    SpeedEvent,
    TemperatureEvent,
    TorqueEvent,
)
from .fault import FaultManager
from .force_sensor import ForceSensorManager
from .speed import SpeedManager
from .temperature import TemperatureManager
from .torque import TorqueManager
from .version import VersionManager

_DEFAULT_POLL_INTERVALS: dict[SensorSource, float] = {
    SensorSource.ANGLE: 1 / 30,
}
_DEFAULT_FRAME_TYPE = 0x04
_THREAD_JOIN_TIMEOUT_S = 2.0


class O20:
    """Main interface for O20 CANFD robotic hand control.

    The O20 class owns the CANFD dispatcher by default and exposes subsystem
    managers for angle, speed, torque, current, temperature, fault, tactile
    force sensors, and DeviceInfo. Two CANFD backends are supported:

    - ``interface_type="ctypes"`` (default): uses the vendor
      ``libcanbus.so`` / ``HCanbus.dll`` adapter. Works on Linux and Windows.
    - ``interface_type="socketcan"``: uses Linux SocketCAN in CAN FD mode via
      python-can. Requires the link to be configured via ``ip link``.

    Use O20 as a context manager so the dispatcher and background workers are
    stopped reliably.

    Vendor adapter (default):

    ```python
    with O20(side="right", library_path="/path/to/libcanbus.so") as hand:
        info = hand.version.get_device_info()
        hand.speed.set_all(50)
        hand.torque.set_all(400)
        hand.angle.set_angles([30] * 16)   # 0-100 percentages, like L6/L30
        print(hand.angle.get_blocking())
    ```

    SocketCAN FD on Linux. Bring the link up first, for example:

    ```bash
    sudo ip link set can0 up type can bitrate 1000000 dbitrate 5000000 fd on
    ```

    Then:

    ```python
    with O20(side="right", interface_type="socketcan", socketcan_channel="can0") as hand:
        print(hand.version.get_device_info())
    ```

    Pass ``auto_reconfigure=True`` to let the SDK run ``ip link`` itself when
    the link is missing or has mismatched bitrates (requires CAP_NET_ADMIN).

    Attributes:
        angle: Manager for joint angle commands and angle sensor data.
        speed: Manager for motor speed commands and speed sensor data.
        torque: Manager for target torque commands.
        current: Manager for motor current sensor data.
        temperature: Manager for temperature sensor data.
        fault: Manager for per-motor fault status bytes and fault clears.
        force_sensor: Manager for tactile force sensor matrices.
        version: Manager for DeviceInfo queries.
    """

    def __init__(
        self,
        side: Literal["left", "right"] = "right",
        device_id: int | None = None,
        device: int = 0,
        channel: int = 0,
        library_path: str | Path | None = None,
        config: CANFDConfigOptions | None = None,
        frame_type: int | None = _DEFAULT_FRAME_TYPE,
        dispatcher: O20DispatcherLike | None = None,
        interface_type: Literal["ctypes", "socketcan"] = "ctypes",
        socketcan_channel: str | None = None,
        bitrate: int = 1_000_000,
        data_bitrate: int = 5_000_000,
        auto_reconfigure: bool = False,
    ) -> None:
        """Initialize the O20 hand interface.

        Args:
            side: Physical hand side ("left" or "right"). Used to derive the
                default device ID when ``device_id`` is not supplied.
            device_id: Optional explicit O20 device ID. When set, takes
                precedence over ``side``. Defaults to ``0x01`` for the right
                hand and ``0x02`` for the left hand.
            device: Vendor CANFD adapter device index. Used when
                ``interface_type="ctypes"``.
            channel: Vendor CANFD adapter channel index. Used when
                ``interface_type="ctypes"``.
            library_path: Path to the vendor CANFD dynamic library. Used when
                ``interface_type="ctypes"``. If omitted, the CANFD backend uses
                its default library lookup order.
            config: CANFD adapter configuration. Used when
                ``interface_type="ctypes"``. If omitted, the CANFD backend uses
                its default nominal/data baud and frame settings.
            frame_type: Optional CANFD frame type override applied to every
                outgoing frame. The O20 hand defaults to 0x04 (CAN FD without
                bit-rate switching); SocketCAN maps 0x04/0x0C to python-can's
                ``bitrate_switch`` flag.
            dispatcher: Optional dispatcher-like transport. Pass this for tests
                or alternate CANFD transports; bypasses every other transport
                argument.
            interface_type: ``"ctypes"`` (default) uses the vendor
                ``libcanbus.so`` / ``HCanbus.dll`` backend. ``"socketcan"``
                uses Linux SocketCAN in CAN FD mode (``socketcan_channel``
                required).
            socketcan_channel: SocketCAN interface name (``"can0"``…).
                Required when ``interface_type="socketcan"``; ignored
                otherwise. The existing ``channel`` parameter is kept as the
                ctypes vendor channel index, so SocketCAN gets its own name.
            bitrate: Nominal bitrate for the SocketCAN backend, defaults to
                1 Mbit/s. Ignored when ``interface_type="ctypes"``.
            data_bitrate: Data-phase bitrate for the SocketCAN backend,
                defaults to 5 Mbit/s. Ignored when ``interface_type="ctypes"``.
            auto_reconfigure: When True with ``interface_type="socketcan"``,
                the SDK runs ``ip link set ... down/up`` itself if the link is
                missing or has mismatched bitrates. Requires
                ``CAP_NET_ADMIN``. Defaults to False (the SDK only inspects
                the link and reports a copyable ``ip link`` command on
                mismatch). Ignored when ``interface_type="ctypes"``.

        Raises:
            ValidationError: If side, device_id, device, channel, or
                ``interface_type`` is invalid.
            CANError: If the CANFD backend cannot be initialized.
        """
        if device_id is None:
            device_id = _device_id_for_side(side)
        protocol._validate_range(device_id, "device_id", 0, protocol.O20_DEVICE_ID_MAX)
        if type(device) is not int:
            raise ValidationError("device must be int")
        if device < 0:
            raise ValidationError("device must be non-negative")
        if type(channel) is not int:
            raise ValidationError("channel must be int")
        if channel < 0:
            raise ValidationError("channel must be non-negative")
        if interface_type not in ("ctypes", "socketcan"):
            raise ValidationError(
                f"interface_type must be 'ctypes' or 'socketcan', got {interface_type!r}"
            )

        # Initialize all simple fields up front so that close() — which may be
        # invoked very early via the on_bus_error callback once the dispatcher
        # starts its receive thread — can safely access every attribute it
        # touches without AttributeError.
        self._bus_error: Exception | None = None
        self._owns_dispatcher = dispatcher is None
        self._closed = False
        self._dispatcher: O20DispatcherLike | None = None
        self._unified_queue: IterableQueue[SensorEvent] | None = None
        self._stop_polling = threading.Event()
        self._stop_polling.set()
        self._polling_threads: dict[SensorSource, threading.Thread] = {}
        self._polling_senders: dict[SensorSource, Callable[[], None]] = {}

        if dispatcher is None:
            dispatcher = self._build_dispatcher(
                interface_type=interface_type,
                device=device,
                channel=channel,
                library_path=library_path,
                config=config,
                socketcan_channel=socketcan_channel,
                bitrate=bitrate,
                data_bitrate=data_bitrate,
                auto_reconfigure=auto_reconfigure,
            )
        self._dispatcher = dispatcher
        try:
            self._client = O20Client(
                dispatcher, device_id=device_id, frame_type=frame_type
            )

            self.angle = AngleManager(self._client)
            self.speed = SpeedManager(self._client)
            self.torque = TorqueManager(self._client)
            self.current = CurrentManager(self._client)
            self.temperature = TemperatureManager(self._client)
            self.fault = FaultManager(self._client)
            self.force_sensor = ForceSensorManager(self._client)
            self.version = VersionManager(self._client)
        except BaseException:
            if self._owns_dispatcher:
                try:
                    self._dispatcher.stop()
                except Exception:
                    pass
            self._closed = True
            raise

        self._polling_senders = {
            SensorSource.ANGLE: self.angle._send_sense_request,
            SensorSource.SPEED: self.speed._send_sense_request,
            SensorSource.CURRENT: self.current._send_sense_request,
            SensorSource.TEMPERATURE: self.temperature._send_sense_request,
            SensorSource.FAULT: self.fault._send_sense_request,
            SensorSource.FORCE_SENSOR: self.force_sensor._send_sense_request,
        }

        self.angle._set_event_sink(lambda data: self._push_event(AngleEvent(data=data)))
        self.speed._set_event_sink(lambda data: self._push_event(SpeedEvent(data=data)))
        self.torque._set_event_sink(
            lambda data: self._push_event(TorqueEvent(data=data))
        )
        self.current._set_event_sink(
            lambda data: self._push_event(CurrentEvent(data=data))
        )
        self.temperature._set_event_sink(
            lambda data: self._push_event(TemperatureEvent(data=data))
        )
        self.fault._set_event_sink(lambda data: self._push_event(FaultEvent(data=data)))
        self.force_sensor._set_event_sink(
            lambda data: self._push_event(ForceSensorEvent(data=data))
        )

    def __enter__(self) -> O20:
        """Enter the context manager.

        Returns:
            Self for use in with statements.
        """
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        """Exit the context manager and release CANFD resources.

        Returns:
            False to propagate exceptions raised inside the with block.
        """
        self.close()
        return False

    @property
    def device_id(self) -> int:
        """O20 device ID used by this hand object."""
        return self._client.device_id

    def get_snapshot(self) -> O20Snapshot:
        """Get the latest cached data from every O20 manager.

        This method is non-blocking. Fields remain None until the corresponding
        manager has received data from a blocking read or host-side poll.

        Returns:
            O20Snapshot containing cached manager data and the snapshot time.
        """
        return O20Snapshot(
            angle=self.angle.get_snapshot(),
            speed=self.speed.get_snapshot(),
            torque=self.torque.get_snapshot(),
            current=self.current.get_snapshot(),
            temperature=self.temperature.get_snapshot(),
            fault=self.fault.get_snapshot(),
            force_sensor=self.force_sensor.get_snapshot(),
            timestamp=time.time(),
        )

    def stream(self, maxsize: int = 100) -> IterableQueue[SensorEvent]:
        """Start a unified event stream for all manager updates.

        Events are pushed when manager snapshots are updated by blocking reads
        or host-side polling. Starting a new stream closes any previous stream.

        Args:
            maxsize: Maximum number of pending events kept in the queue.

        Returns:
            Iterable queue yielding SensorEvent instances.

        Raises:
            CANError: If the CANFD bus has failed.
            StateError: If the O20 interface is closed.
        """
        self._ensure_open()
        if self._unified_queue is not None:
            self.stop_stream()
        self._unified_queue = IterableQueue(maxsize=maxsize)
        return self._unified_queue

    def stop_stream(self) -> None:
        """Stop the unified event stream if one is active."""
        if self._unified_queue is None:
            return
        self._unified_queue.close()
        self._unified_queue = None

    def start_polling(
        self, intervals: dict[SensorSource, float] = _DEFAULT_POLL_INTERVALS
    ) -> None:
        """Start host-side polling for selected sensor sources.

        Each selected source is read in a background thread and updates the
        same manager cache and unified event stream used by blocking reads.

        Args:
            intervals: Mapping of sensor source to poll interval in seconds.

        Raises:
            CANError: If the CANFD bus has failed.
            StateError: If the O20 interface is closed.
            ValidationError: If an interval is not positive or the source cannot
                be polled by the host.
        """
        self._ensure_open()
        if not self._stop_polling.is_set():
            self.stop_polling()
        for source, interval in intervals.items():
            if not isinstance(source, SensorSource):
                raise ValidationError("polling source must be SensorSource")
            if interval <= 0:
                raise ValidationError(
                    f"Interval for {source.value} must be positive, got {interval}"
                )
            if source not in self._polling_senders:
                raise ValidationError(f"Unsupported polling source {source.value}")
        self._stop_polling.clear()
        try:
            for source, interval in intervals.items():
                thread = threading.Thread(
                    target=self._polling_loop,
                    args=(source, interval),
                    daemon=True,
                    name=f"O20-Polling-{source.value}",
                )
                thread.start()
                self._polling_threads[source] = thread
        except BaseException:
            self.stop_polling()
            raise

    def stop_polling(self) -> None:
        """Stop all host-side polling threads."""
        self._stop_polling.set()
        for thread in self._polling_threads.values():
            thread.join(timeout=_THREAD_JOIN_TIMEOUT_S)
        self._polling_threads.clear()

    def close(self) -> None:
        """Release stream, polling, manager, client, and owned dispatcher resources.

        This method is idempotent. ``_closed`` is set before any release runs so
        a re-entry (for example from ``__del__`` after a partial failure) returns
        immediately rather than retrying half-released resources. Each owned
        attribute is consulted via ``getattr`` so close() can also run safely if
        ``__init__`` was interrupted before all fields were assigned (for
        example via an early ``on_bus_error`` callback).
        """
        if self._closed:
            return
        self._closed = True
        if hasattr(self, "_stop_polling"):
            self.stop_polling()
        if getattr(self, "_unified_queue", None) is not None:
            self.stop_stream()
        for attr in (
            "angle",
            "speed",
            "torque",
            "current",
            "temperature",
            "fault",
            "force_sensor",
        ):
            manager = getattr(self, attr, None)
            if manager is not None:
                manager.close()
        client = getattr(self, "_client", None)
        if client is not None:
            client.close()
        if getattr(self, "_owns_dispatcher", False):
            dispatcher = getattr(self, "_dispatcher", None)
            if dispatcher is not None:
                dispatcher.stop()

    def __del__(self) -> None:
        # close() can fail at GC time for many reasons (interpreter shutdown,
        # already-finalised dependencies, hardware errors). __del__ is best
        # effort, so swallow any error rather than letting Python print
        # "Exception ignored in __del__" noise on exit.
        if not hasattr(self, "_closed"):
            return
        try:
            self.close()
        except BaseException:
            pass

    def is_closed(self) -> bool:
        """Return whether this O20 interface has been closed or lost its bus."""
        return self._closed

    def _on_bus_error(self, error: Exception) -> None:
        self._bus_error = error
        self.close()

    def _build_dispatcher(
        self,
        *,
        interface_type: str,
        device: int,
        channel: int,
        library_path: str | Path | None,
        config: CANFDConfigOptions | None,
        socketcan_channel: str | None,
        bitrate: int,
        data_bitrate: int,
        auto_reconfigure: bool,
    ) -> CANFDMessageDispatcher:
        if interface_type == "ctypes":
            return CANFDMessageDispatcher(
                device_index=device,
                channel_index=channel,
                library_path=library_path,
                config=config,
                on_bus_error=self._on_bus_error,
            )
        if socketcan_channel is None:
            raise ValidationError(
                "interface_type='socketcan' requires "
                "socketcan_channel (e.g. socketcan_channel='can0')"
            )
        backend = SocketCANFDBackend(
            channel=socketcan_channel,
            bitrate=bitrate,
            data_bitrate=data_bitrate,
            auto_reconfigure=auto_reconfigure,
        )
        return CANFDMessageDispatcher(
            interface=backend, on_bus_error=self._on_bus_error
        )

    def _ensure_open(self) -> None:
        if self._bus_error is not None:
            raise CANError(f"CANFD bus unavailable: {self._bus_error}")
        if self._closed:
            raise StateError(
                "O20 interface is closed. Create a new instance or use context manager."
            )

    def _polling_loop(self, source: SensorSource, interval: float) -> None:
        sender = self._polling_senders[source]
        while not self._stop_polling.is_set():
            try:
                sender()
            except LinkerbotError:
                pass
            self._stop_polling.wait(interval)

    def _push_event(self, event: SensorEvent) -> None:
        event_queue = self._unified_queue
        if event_queue is None:
            return
        try:
            event_queue.put_nowait(event)
        except (queue.Full, StateError):
            try:
                event_queue.get_nowait()
            except queue.Empty:
                pass
            try:
                event_queue.put_nowait(event)
            except (queue.Full, StateError):
                pass


def _device_id_for_side(side: str) -> int:
    if side == "right":
        return protocol.O20_DEVICE_ID_RIGHT
    if side == "left":
        return protocol.O20_DEVICE_ID_LEFT
    raise ValidationError(f"side must be 'left' or 'right', got {side!r}")
