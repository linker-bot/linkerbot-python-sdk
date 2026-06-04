"""L30 robotic hand control interface.

This module provides the main L30 class for controlling the L30 CANFD robotic hand.
It integrates control commands, joint targets, sensor reads, device-side periodic
reports, host-side polling, and unified event streaming into a single SDK entry.
"""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable
from pathlib import Path

from linkerbot.comm.canfd import CANFDConfigOptions, CANFDMessageDispatcher
from linkerbot.exceptions import CANError, LinkerbotError, StateError, ValidationError
from linkerbot.queue import IterableQueue

from . import protocol
from .angle import AngleManager
from .client import L30Client, L30DispatcherLike
from .control import ControlManager
from .current import CurrentManager
from .events import (
    AngleEvent,
    CurrentEvent,
    FaultEvent,
    ForceSensorEvent,
    L30Snapshot,
    SensorEvent,
    SensorSource,
    SpeedEvent,
    TemperatureEvent,
    TorqueEvent,
)
from .fault import FaultManager
from .force_sensor import ForceSensorManager
from .report import ReportManager
from .speed import SpeedManager
from .temperature import TemperatureManager
from .torque import TorqueManager
from .version import VersionManager

_DEFAULT_POLL_INTERVALS: dict[SensorSource, float] = {
    SensorSource.ANGLE: 1 / 60,
}
_DEFAULT_PERIODIC_TIMEOUT_MS = 100
_THREAD_JOIN_TIMEOUT_S = 2.0


class L30:
    """Main interface for L30 CANFD robotic hand control.

    The L30 class owns the CANFD dispatcher by default and exposes subsystem
    managers for control, angle, speed, torque, current, temperature, fault,
    tactile force sensors, and device-side periodic reports. It can also accept
    an injected dispatcher for tests or future CANFD backends such as socketcan-fd.

    Use L30 as a context manager so the dispatcher and background workers are
    stopped reliably:

    ```python
    with L30(library_path="/path/to/libcanbus.so") as hand:
        angles = hand.angle.get_blocking(timeout_ms=1000)
        print(angles.angles.to_list())

        for event in hand.stream():
            print(event)
            break
    ```

    Attributes:
        control: Manager for enable and disable commands.
        angle: Manager for joint angle commands and angle sensor data.
        speed: Manager for motor speed commands and speed sensor data.
        torque: Manager for target torque commands.
        current: Manager for current sensor data.
        temperature: Manager for temperature sensor data.
        fault: Manager for per-joint fault status bytes.
        force_sensor: Manager for tactile force sensor matrices.
        report: Manager for device-side periodic report configuration.
        version: Manager for DeviceInfo, product code, NodeID, and hand-side queries.
    """

    def __init__(
        self,
        node_id: int = 1,
        host_id: int = 0,
        device_index: int = 0,
        channel_index: int = 0,
        library_path: str | Path | None = None,
        config: CANFDConfigOptions | None = None,
        auto_start_periodic: bool = True,
        dispatcher: L30DispatcherLike | None = None,
    ) -> None:
        """Initialize the L30 hand interface.

        Args:
            node_id: L30 device node ID used as CANFD destination ID.
            host_id: Host node ID used as CANFD source ID.
            device_index: Vendor CANFD adapter device index.
            channel_index: Vendor CANFD adapter channel index.
            library_path: Path to the vendor CANFD dynamic library. If omitted,
                the CANFD backend uses its default library lookup.
            config: CANFD adapter configuration. If omitted, the CANFD backend
                uses its default nominal/data baud and frame settings.
            auto_start_periodic: Whether to enable the default angle periodic
                report immediately after initialization.
            dispatcher: Optional dispatcher-like transport. Pass this for tests
                or alternate CANFD transports while keeping L30 protocol logic
                unchanged.

        Raises:
            ValidationError: If node, host, device, or channel IDs are invalid.
            CANError: If the CANFD backend cannot be initialized.
        """
        protocol._validate_range(
            node_id, "node_id", protocol.L30_NODE_ID_MIN, protocol.L30_NODE_ID_MAX
        )
        protocol._validate_range(
            host_id, "host_id", protocol.L30_HOST_ID_MIN, protocol.L30_HOST_ID_MAX
        )
        if type(device_index) is not int:
            raise ValidationError("device_index must be int")
        if device_index < 0:
            raise ValidationError("device_index must be non-negative")
        if type(channel_index) is not int:
            raise ValidationError("channel_index must be int")
        if channel_index < 0:
            raise ValidationError("channel_index must be non-negative")

        self._bus_error: Exception | None = None
        self._owns_dispatcher = dispatcher is None
        if dispatcher is None:
            dispatcher = CANFDMessageDispatcher(
                device_index=device_index,
                channel_index=channel_index,
                library_path=library_path,
                config=config,
                on_bus_error=self._on_bus_error,
            )
        self._dispatcher = dispatcher
        self._client = L30Client(dispatcher, node_id=node_id, host_id=host_id)

        self.control = ControlManager(self._client)
        self.angle = AngleManager(self._client)
        self.speed = SpeedManager(self._client)
        self.torque = TorqueManager(self._client)
        self.current = CurrentManager(self._client)
        self.temperature = TemperatureManager(self._client)
        self.fault = FaultManager(self._client)
        self.force_sensor = ForceSensorManager(self._client)
        self.report = ReportManager(self._client)
        self.version = VersionManager(self._client)

        self._closed = False
        self._unified_queue: IterableQueue[SensorEvent] | None = None
        self._stop_polling = threading.Event()
        self._stop_polling.set()
        self._polling_threads: dict[str, threading.Thread] = {}
        self._polling_senders: dict[str, Callable[[], None]] = {
            SensorSource.ANGLE.value: self.angle._send_sense_request,
            SensorSource.SPEED.value: self.speed._send_sense_request,
            SensorSource.CURRENT.value: self.current._send_sense_request,
            SensorSource.TEMPERATURE.value: self.temperature._send_sense_request,
            SensorSource.FAULT.value: self.fault._send_sense_request,
            SensorSource.FORCE_SENSOR.value: self.force_sensor._send_sense_request,
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

        if auto_start_periodic:
            self.start_periodic_reports(timeout_ms=_DEFAULT_PERIODIC_TIMEOUT_MS)

    def __enter__(self) -> L30:
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
    def node_id(self) -> int:
        """L30 device node ID used by this hand object."""
        return self._client.node_id

    @property
    def host_id(self) -> int:
        """Host node ID used by this hand object."""
        return self._client.host_id

    def get_snapshot(self) -> L30Snapshot:
        """Get the latest cached data from every L30 manager.

        This method is non-blocking. Fields remain None until the corresponding
        manager has received data from a blocking read, host-side poll, or
        device-side periodic report.

        Returns:
            L30Snapshot containing cached manager data and the snapshot time.
        """
        return L30Snapshot(
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

        Events are pushed when manager snapshots are updated by blocking reads,
        host-side polling, or device-side periodic reports. Starting a new stream
        closes any previous stream.

        Args:
            maxsize: Maximum number of pending events kept in the queue.

        Returns:
            Iterable queue yielding SensorEvent instances.

        Raises:
            CANError: If the CANFD bus has failed.
            StateError: If the L30 interface is closed.
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

    def start_periodic_reports(self, *, timeout_ms: float = 100) -> None:
        """Enable the default device-side periodic reports.

        The current default configures angle reports. Additional report sources
        can be configured directly through the report manager.

        Args:
            timeout_ms: Time to wait for the periodic configuration ACK.

        Raises:
            CANError: If the CANFD bus has failed.
            StateError: If the L30 interface is closed.
            ValidationError: If timeout_ms is invalid.
        """
        self._ensure_open()
        self.report.start_default(timeout_ms=timeout_ms)

    def stop_periodic_reports(self, *, timeout_ms: float = 100) -> None:
        """Disable all device-side periodic report sources.

        Args:
            timeout_ms: Time to wait for each disable ACK.

        Raises:
            CANError: If the CANFD bus has failed.
            StateError: If the L30 interface is closed.
            ValidationError: If timeout_ms is invalid.
        """
        self._ensure_open()
        self.report.disable_all(timeout_ms=timeout_ms)

    def start_polling(
        self, intervals: dict[SensorSource, float] = _DEFAULT_POLL_INTERVALS
    ) -> None:
        """Start host-side polling for selected sensor sources.

        Polling is an alternative to device-side periodic reports. Each selected
        source is read in a background thread and updates the same manager cache
        and unified event stream used by blocking reads.

        Args:
            intervals: Mapping of sensor source to poll interval in seconds.

        Raises:
            CANError: If the CANFD bus has failed.
            StateError: If the L30 interface is closed.
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
            if source.value not in self._polling_senders:
                raise ValidationError(f"Unsupported polling source {source.value}")
        self._stop_polling.clear()
        for source, interval in intervals.items():
            thread = threading.Thread(
                target=self._polling_loop,
                args=(source.value, interval),
                daemon=True,
                name=f"L30-Polling-{source.value}",
            )
            thread.start()
            self._polling_threads[source.value] = thread

    def stop_polling(self) -> None:
        """Stop all host-side polling threads."""
        self._stop_polling.set()
        for thread in self._polling_threads.values():
            thread.join(timeout=_THREAD_JOIN_TIMEOUT_S)
        self._polling_threads.clear()

    def close(self) -> None:
        """Release stream, polling, manager, client, and owned dispatcher resources.

        This method is idempotent. It does not send an L30 disable command; call
        control.disable() explicitly when the hardware should be disabled.
        """
        if self._closed:
            return
        if self._bus_error is None:
            try:
                self.report.disable_all(timeout_ms=_DEFAULT_PERIODIC_TIMEOUT_MS)
            except LinkerbotError:
                pass
        self.stop_polling()
        self.stop_stream()
        for manager in (
            self.angle,
            self.speed,
            self.current,
            self.temperature,
            self.fault,
        ):
            manager.close()
        self._client.close()
        if self._owns_dispatcher:
            self._dispatcher.stop()
        self._closed = True

    def __del__(self) -> None:
        if hasattr(self, "_closed"):
            self.close()

    def is_closed(self) -> bool:
        """Return whether this L30 interface has been closed or lost its bus."""
        return self._closed

    def _on_bus_error(self, error: Exception) -> None:
        self._bus_error = error
        self.close()

    def _ensure_open(self) -> None:
        if self._bus_error is not None:
            raise CANError(f"CANFD bus unavailable: {self._bus_error}")
        if self._closed:
            raise StateError(
                "L30 interface is closed. Create a new instance or use context manager."
            )

    def _polling_loop(self, source_name: str, interval: float) -> None:
        sender = self._polling_senders[source_name]
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
