"""High-level O30i interface on top of HandProtocol_v1.0."""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Literal

from linkerbot.comm.canfd import (
    CANFDConfigOptions,
    CANFDMessageDispatcher,
    SocketCANFDBackend,
)
from linkerbot.exceptions import CANError, LinkerbotError, StateError, ValidationError
from linkerbot.hand.hand_protocol_v1 import (
    HandProtocolV1,
    HandProtocolV1DispatcherLike,
)
from linkerbot.queue import IterableQueue

from . import protocol
from .acceleration import AccelerationManager
from .angle import AngleManager
from .current import CurrentManager
from .diagnostics import DiagnosticsManager
from .events import (
    AccelerationEvent,
    AngleEvent,
    CurrentEvent,
    FaultEvent,
    MotionTimeEvent,
    O30iSnapshot,
    SensorEvent,
    SensorSource,
    SpeedEvent,
    TemperatureEvent,
    TorqueEvent,
    VoltageEvent,
)
from .fault import FaultManager
from .motion_time import MotionTimeManager
from .sensor import SensorManager
from .speed import SpeedManager
from .temperature import TemperatureManager
from .torque import TorqueManager
from .version import VersionManager
from .voltage import VoltageManager

_DEFAULT_POLL_INTERVALS: Mapping[SensorSource, float] = {
    SensorSource.ANGLE: 1 / 30,
}
_THREAD_JOIN_TIMEOUT_S = 2.0


class O30i:
    """O30i robotic hand using the measured HandProtocol_v1.0/HOP behavior.

    The default backend remains the vendor ``libcanbus.so`` / ``HCanbus.dll``
    ctypes adapter. Linux callers can opt into python-can SocketCAN with
    ``interface_type="socketcan"`` and ``socketcan_channel="can0"``.

    The public ``protocol`` attribute exposes the transport-neutral HOP object
    layer for advanced, read-oriented access. High-level managers deliberately
    omit unreliable mapping/enable objects and dangerous engineering/config
    writes documented by the measured firmware report.

    Attributes:
        protocol: Serialized, transport-neutral HandProtocol_v1.0 client.
        angle: Position commands and actual/target position reads.
        speed: Raw speed-byte commands and state reads.
        acceleration: Raw acceleration-byte commands and state reads.
        current: Read-only current-state manager.
        voltage: Read-only voltage-state manager.
        torque: Raw torque-byte commands and state reads.
        temperature: Read-only temperature-state manager.
        motion_time: Motion-duration commands and reads (10 ms per tick).
        fault: Read-only raw per-slot fault state.
        version: Product and firmware identity reads.
        sensor: Sensor-capability metadata reads.
        diagnostics: Communication-error history reads.
    """

    def __init__(
        self,
        *,
        request_id: int = protocol.O30I_REQUEST_ID,
        response_id: int | None = None,
        device: int = 0,
        channel: int = 0,
        library_path: str | Path | None = None,
        config: CANFDConfigOptions | None = None,
        frame_type: int | None = protocol.O30I_FRAME_TYPE,
        dispatcher: HandProtocolV1DispatcherLike | None = None,
        interface_type: Literal["ctypes", "socketcan"] = "ctypes",
        socketcan_channel: str | None = None,
        bitrate: int = 1_000_000,
        data_bitrate: int = 5_000_000,
        auto_reconfigure: bool = False,
    ) -> None:
        """Open one O30i endpoint and construct all safe managers.

        Args:
            request_id: Standard CAN ID used for HOP requests. Defaults to the
                measured O30i endpoint ``0x001``.
            response_id: Standard CAN ID expected for responses. ``None``
                derives ``request_id | 0x400``; explicit IDs may use the full
                11-bit range.
            device: Vendor CAN FD adapter index for the ctypes backend.
            channel: Vendor CAN FD adapter channel for the ctypes backend.
            library_path: Optional ``libcanbus.so`` / ``HCanbus.dll`` path.
            config: Optional vendor-adapter CAN FD configuration.
            frame_type: Outgoing vendor FrameType byte. The measured default
                is ``0x04`` (CAN FD without bit-rate switching).
            dispatcher: Existing dispatcher for tests, custom transports, or
                shared buses. When supplied, the O30i does not own or stop it.
            interface_type: ``"ctypes"`` for the vendor library or
                ``"socketcan"`` for python-can on Linux.
            socketcan_channel: SocketCAN interface name such as ``"can0"``;
                required for the SocketCAN backend.
            bitrate: SocketCAN nominal bitrate in bits per second.
            data_bitrate: SocketCAN data-phase configuration in bits per
                second. O30i frames do not enable BRS, but the Linux FD link
                still exposes this setting.
            auto_reconfigure: Allow the SocketCAN backend to run ``ip link``
                when the interface configuration differs. Requires network
                administration permission.

        Raises:
            ValidationError: If endpoint or backend arguments are invalid.
            CANError: If the selected CAN FD backend cannot be opened.
        """
        _validate_non_negative_int(device, "device")
        _validate_non_negative_int(channel, "channel")
        if interface_type not in ("ctypes", "socketcan"):
            raise ValidationError(
                "interface_type must be 'ctypes' or 'socketcan', "
                f"got {interface_type!r}"
            )

        # Validate endpoint IDs before opening a physical adapter so a typo
        # cannot allocate threads or USB resources and then fail afterwards.
        _validate_standard_id(request_id, "request_id")
        if response_id is None:
            if request_id > 0x3FF:
                raise ValidationError("request_id must be between 0 and 1023")
        else:
            _validate_standard_id(response_id, "response_id")
            if request_id == response_id:
                raise ValidationError("request_id and response_id must be different")
        if frame_type is not None:
            if not isinstance(frame_type, int) or isinstance(frame_type, bool):
                raise ValidationError("frame_type must be int")
            if frame_type < 0 or frame_type > 0xFF:
                raise ValidationError("frame_type must be between 0 and 255")

        self._bus_error: Exception | None = None
        self._owns_dispatcher = dispatcher is None
        self._closed = False
        self._dispatcher: HandProtocolV1DispatcherLike | None = None
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
            self.protocol = HandProtocolV1(
                dispatcher,
                request_id=request_id,
                response_id=response_id,
                frame_type=frame_type,
            )
            self.angle = AngleManager(self.protocol)
            self.speed = SpeedManager(self.protocol)
            self.acceleration = AccelerationManager(self.protocol)
            self.current = CurrentManager(self.protocol)
            self.voltage = VoltageManager(self.protocol)
            self.torque = TorqueManager(self.protocol)
            self.temperature = TemperatureManager(self.protocol)
            self.motion_time = MotionTimeManager(self.protocol)
            self.fault = FaultManager(self.protocol)
            self.version = VersionManager(self.protocol)
            self.sensor = SensorManager(self.protocol)
            self.diagnostics = DiagnosticsManager(self.protocol)
        except BaseException:
            if self._owns_dispatcher:
                try:
                    dispatcher.stop()
                except Exception:
                    pass
            self._closed = True
            raise

        self._polling_senders = {
            SensorSource.ANGLE: self.angle._send_sense_request,
            SensorSource.SPEED: self.speed._send_sense_request,
            SensorSource.ACCELERATION: self.acceleration._send_sense_request,
            SensorSource.CURRENT: self.current._send_sense_request,
            SensorSource.VOLTAGE: self.voltage._send_sense_request,
            SensorSource.TORQUE: self.torque._send_sense_request,
            SensorSource.TEMPERATURE: self.temperature._send_sense_request,
            SensorSource.MOTION_TIME: self.motion_time._send_sense_request,
            SensorSource.FAULT: self.fault._send_sense_request,
        }
        self.angle._set_event_sink(lambda data: self._push_event(AngleEvent(data)))
        self.speed._set_event_sink(lambda data: self._push_event(SpeedEvent(data)))
        self.acceleration._set_event_sink(
            lambda data: self._push_event(AccelerationEvent(data))
        )
        self.current._set_event_sink(lambda data: self._push_event(CurrentEvent(data)))
        self.voltage._set_event_sink(lambda data: self._push_event(VoltageEvent(data)))
        self.torque._set_event_sink(lambda data: self._push_event(TorqueEvent(data)))
        self.temperature._set_event_sink(
            lambda data: self._push_event(TemperatureEvent(data))
        )
        self.motion_time._set_event_sink(
            lambda data: self._push_event(MotionTimeEvent(data))
        )
        self.fault._set_event_sink(lambda data: self._push_event(FaultEvent(data)))

    @property
    def request_id(self) -> int:
        return self.protocol.request_id

    @property
    def response_id(self) -> int:
        return self.protocol.response_id

    def __enter__(self) -> O30i:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        self.close()
        return False

    def get_snapshot(self) -> O30iSnapshot:
        """Return current manager caches without issuing bus requests."""
        return O30iSnapshot(
            angle=self.angle.get_snapshot(),
            speed=self.speed.get_snapshot(),
            acceleration=self.acceleration.get_snapshot(),
            current=self.current.get_snapshot(),
            voltage=self.voltage.get_snapshot(),
            torque=self.torque.get_snapshot(),
            temperature=self.temperature.get_snapshot(),
            motion_time=self.motion_time.get_snapshot(),
            fault=self.fault.get_snapshot(),
            timestamp=time.time(),
        )

    def stream(self, maxsize: int = 100) -> IterableQueue[SensorEvent]:
        self._ensure_open()
        if self._unified_queue is not None:
            self.stop_stream()
        self._unified_queue = IterableQueue(maxsize=maxsize)
        return self._unified_queue

    def stop_stream(self) -> None:
        if self._unified_queue is None:
            return
        self._unified_queue.close()
        self._unified_queue = None

    def start_polling(
        self,
        intervals: Mapping[SensorSource, float] | None = None,
    ) -> None:
        """Start one host polling thread per requested runtime object."""
        self._ensure_open()
        selected = dict(_DEFAULT_POLL_INTERVALS if intervals is None else intervals)
        if not self._stop_polling.is_set():
            self.stop_polling()
        for source, interval in selected.items():
            if not isinstance(source, SensorSource):
                raise ValidationError("polling source must be SensorSource")
            if not isinstance(interval, (int, float)) or isinstance(interval, bool):
                raise ValidationError(f"interval for {source.value} must be numeric")
            if interval <= 0:
                raise ValidationError(f"interval for {source.value} must be positive")
        self._stop_polling.clear()
        try:
            for source, interval in selected.items():
                thread = threading.Thread(
                    target=self._polling_loop,
                    args=(source, float(interval)),
                    daemon=True,
                    name=f"O30i-Polling-{source.value}",
                )
                thread.start()
                self._polling_threads[source] = thread
        except BaseException:
            self.stop_polling()
            raise

    def stop_polling(self) -> None:
        self._stop_polling.set()
        for thread in self._polling_threads.values():
            thread.join(timeout=_THREAD_JOIN_TIMEOUT_S)
        self._polling_threads.clear()

    def close(self) -> None:
        """Release all SDK-owned resources. Idempotent and partial-init safe."""
        if self._closed:
            return
        self._closed = True
        self.stop_polling()
        if self._unified_queue is not None:
            self.stop_stream()
        for name in (
            "angle",
            "speed",
            "acceleration",
            "current",
            "voltage",
            "torque",
            "temperature",
            "motion_time",
            "fault",
        ):
            manager = getattr(self, name, None)
            if manager is not None:
                manager.close()
        client = getattr(self, "protocol", None)
        if client is not None:
            client.close()
        if self._owns_dispatcher and self._dispatcher is not None:
            self._dispatcher.stop()

    def __del__(self) -> None:
        if not hasattr(self, "_closed"):
            return
        try:
            self.close()
        except BaseException:
            pass

    def is_closed(self) -> bool:
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
                "interface_type='socketcan' requires socketcan_channel, "
                "for example socketcan_channel='can0'"
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
            raise StateError("O30i interface is closed")

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


def _validate_non_negative_int(value: int, name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValidationError(f"{name} must be int")
    if value < 0:
        raise ValidationError(f"{name} must be non-negative")


def _validate_standard_id(value: int, name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValidationError(f"{name} must be int")
    if value < 0 or value > 0x7FF:
        raise ValidationError(f"{name} must be an 11-bit standard CAN ID")
