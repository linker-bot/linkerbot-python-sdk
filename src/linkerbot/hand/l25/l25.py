"""L25 robotic hand control interface.

This module provides the main L25 class for controlling the L25 robotic hand
via CAN bus communication. It integrates angle control, speed control, torque control,
temperature sensing, fault management, force sensor data acquisition, and unified
sensor streaming into a single interface.
"""

import queue
import threading
import time
from collections.abc import Callable
from typing import Literal

from linkerbot.comm import CanInterface, CANMessageDispatcher
from linkerbot.exceptions import CANError, StateError, ValidationError
from linkerbot.queue import IterableQueue

from .angle import AngleManager
from .events import (
    AngleEvent,
    FaultEvent,
    ForceSensorEvent,
    L25Snapshot,
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
    SensorSource.ANGLE: 1 / 60,
    SensorSource.FORCE_SENSOR: 1 / 30,
}


class L25:
    """Main interface for L25 robotic hand control.

    This class provides a unified interface for controlling the L25 robotic hand,
    integrating angle control, speed control, torque control, temperature sensing,
    fault management, sensor data acquisition, and unified sensor streaming.

    The L25 class should be used as a context manager to ensure proper resource
    cleanup:

    ```python
    with L25(side='left', interface_name='can0') as hand:
        # Control angles
        hand.angle.set_angles([50.0] * 16)

        # Start polling sensors
        hand.start_polling({SensorSource.ANGLE: 0.05, SensorSource.TEMPERATURE: 1.0})

        # Read cached data
        snap = hand.get_snapshot()
        print(snap.angle, snap.temperature)

        # Stream all events
        for event in hand.stream():
            match event:
                case AngleEvent(data=ad):
                    print(f"Angles: {ad.angles}")
                case TemperatureEvent(data=td):
                    print(f"Temps: {td.temperatures}")
            if should_stop():
                break

        hand.stop_polling()
        hand.stop_stream()
    ```

    Attributes:
        angle: AngleManager instance for joint angle control and sensing.
        speed: SpeedManager instance for motor speed control and sensing.
        torque: TorqueManager instance for joint torque control and sensing.
        temperature: TemperatureManager instance for temperature data acquisition.
        fault: FaultManager instance for fault clearing and status reading.
        force_sensor: ForceSensorManager instance for force sensor data acquisition.
        version: VersionManager instance for device version information.

    Args:
        side: Side of the hand (left or right, default: left).
        interface_name: Name of the CAN interface (e.g., 'can0', 'vcan0').
        interface_type: Type of CAN interface backend (default: 'socketcan').
    """

    def __init__(
        self,
        side: Literal["left", "right"],
        interface_name: str,
        interface_type: str = "socketcan",
    ) -> None:
        """Initialize the L25 robotic hand interface.

        Args:
            side: Side of the hand (left or right, default: left).
            interface_name: Name of the CAN interface (e.g., 'can0', 'vcan0').
            interface_type: Type of CAN interface backend (default: 'socketcan').
        """
        # Create CAN message dispatcher
        self._bus_error: Exception | None = None
        self._dispatcher = CANMessageDispatcher(
            interface_name=interface_name,
            interface_type=interface_type,
            on_bus_error=self._on_bus_error,
        )

        if side not in ("left", "right"):
            raise ValidationError(f"side must be 'left' or 'right', got {side!r}")
        self._arbitration_id = 0x27 if side == "right" else 0x28

        # Create subsystem managers
        self.angle = AngleManager(
            arbitration_id=self._arbitration_id, dispatcher=self._dispatcher
        )
        self.speed = SpeedManager(
            arbitration_id=self._arbitration_id, dispatcher=self._dispatcher
        )
        self.torque = TorqueManager(
            arbitration_id=self._arbitration_id, dispatcher=self._dispatcher
        )
        self.temperature = TemperatureManager(
            arbitration_id=self._arbitration_id, dispatcher=self._dispatcher
        )
        self.fault = FaultManager(
            arbitration_id=self._arbitration_id, dispatcher=self._dispatcher
        )
        self.force_sensor = ForceSensorManager(
            arbitration_id=self._arbitration_id, dispatcher=self._dispatcher
        )
        self.version = VersionManager(
            arbitration_id=self._arbitration_id, dispatcher=self._dispatcher
        )
        # State tracking
        self._closed = False

        # Unified stream
        self._unified_queue: IterableQueue[SensorEvent] | None = None

        # Polling
        self._stop_polling = threading.Event()
        self._stop_polling.set()
        self._polling_threads: dict[str, threading.Thread] = {}

        self._polling_senders: dict[str, Callable[[], None]] = {
            "angle": self.angle._send_sense_request,
            "speed": self.speed._send_sense_request,
            "torque": self.torque._send_sense_request,
            "temperature": self.temperature._send_sense_request,
            "fault": self.fault._send_sense_request,
            "force_sensor": self.force_sensor._send_sense_request,
        }

        # Register event sinks
        self.angle._set_event_sink(lambda d: self._push_event(AngleEvent(data=d)))
        self.speed._set_event_sink(lambda d: self._push_event(SpeedEvent(data=d)))
        self.torque._set_event_sink(lambda d: self._push_event(TorqueEvent(data=d)))
        self.temperature._set_event_sink(
            lambda d: self._push_event(TemperatureEvent(data=d))
        )
        self.fault._set_event_sink(lambda d: self._push_event(FaultEvent(data=d)))
        self.force_sensor._set_event_sink(
            lambda d: self._push_event(ForceSensorEvent(data=d))
        )

        # Auto-start default polling
        self.start_polling()

    @property
    def can_interface(self) -> CanInterface:
        """CAN interface this hand is bound to."""
        return self._dispatcher.can_interface

    def __enter__(self) -> "L25":
        """Enter the context manager.

        Returns:
            Self for use in with statements.
        """
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        """Exit the context manager and clean up resources.

        Returns:
            False to propagate exceptions.
        """
        self.close()
        return False

    # ===== Unified snapshot =====

    def get_snapshot(self) -> L25Snapshot:
        """Get all sensor data as a single snapshot (non-blocking).

        Returns:
            L25Snapshot with the latest cached data from all sensors.
            Individual fields are None if no data has been received yet.
        """
        return L25Snapshot(
            angle=self.angle.get_snapshot(),
            speed=self.speed.get_snapshot(),
            torque=self.torque.get_snapshot(),
            temperature=self.temperature.get_snapshot(),
            fault=self.fault.get_snapshot(),
            force_sensor=self.force_sensor.get_snapshot(),
            timestamp=time.time(),
        )

    # ===== Unified stream =====

    def stream(self, maxsize: int = 100) -> IterableQueue[SensorEvent]:
        """Start unified event stream, delivering all sensor responses.

        Returns an IterableQueue that receives SensorEvent instances.
        Use match-case to dispatch by event type.

        Calling stream() again automatically closes the previous queue.

        Args:
            maxsize: Maximum queue size (default: 100). When full, oldest event is dropped.

        Returns:
            IterableQueue[SensorEvent] for receiving sensor events.
        """
        self._ensure_open()
        if self._unified_queue is not None:
            self.stop_stream()
        self._unified_queue = IterableQueue(maxsize=maxsize)
        return self._unified_queue

    def stop_stream(self) -> None:
        """Stop the unified event stream.

        Closes the queue, causing any active for-loop to exit.
        Idempotent: safe to call multiple times.
        """
        if self._unified_queue is None:
            return
        self._unified_queue.close()
        self._unified_queue = None

    # ===== Polling control =====

    def start_polling(
        self,
        intervals: dict[SensorSource, float] = _DEFAULT_POLL_INTERVALS,
    ) -> None:
        """Start background polling for sensor data.

        Polling sends periodic query requests to the specified sensors.
        Responses are cached (readable via get_snapshot()) and pushed
        to the stream if active.

        Calling start_polling() again automatically stops the previous polling.

        Args:
            intervals: Per-sensor polling intervals in seconds.
                Defaults to all sensors at model-specific intervals.

        Raises:
            ValidationError: If any interval is not positive.
        """
        self._ensure_open()
        if not self._stop_polling.is_set():
            self.stop_polling()
        for source, interval in intervals.items():
            if interval <= 0:
                raise ValidationError(
                    f"Interval for {source.value} must be positive, got {interval}"
                )
        self._stop_polling.clear()
        for source, interval in intervals.items():
            t = threading.Thread(
                target=self._polling_loop,
                args=(source.value, interval),
                daemon=True,
                name=f"L25-Polling-{source.value}",
            )
            t.start()
            self._polling_threads[source.value] = t

    def stop_polling(self) -> None:
        """Stop all background polling.

        Idempotent: safe to call multiple times.
        """
        self._stop_polling.set()
        for t in self._polling_threads.values():
            t.join(timeout=2.0)
        self._polling_threads.clear()

    # ===== Lifecycle =====

    def close(self) -> None:
        """Close the L25 interface and release all resources.

        This method is idempotent and safe to call multiple times.
        """
        if self._closed:
            return

        self.stop_polling()
        self.stop_stream()

        try:
            self._dispatcher.stop()
        except Exception:
            pass

        self._closed = True

    def __del__(self) -> None:
        """Destructor for defensive resource cleanup."""
        self.close()

    def is_closed(self) -> bool:
        """Check if the interface has been closed.

        Returns:
            True if the interface is closed, False otherwise.
        """
        return self._closed

    def _on_bus_error(self, error: Exception) -> None:
        self._bus_error = error
        self._closed = True

    def _ensure_open(self) -> None:
        if self._bus_error is not None:
            raise CANError(f"CAN bus unavailable: {self._bus_error}")
        if self._closed:
            raise StateError(
                "L25 interface is closed. Create a new instance or use context manager."
            )

    # ===== Internal =====

    def _polling_loop(self, source_name: str, interval: float) -> None:
        sender = self._polling_senders[source_name]
        while not self._stop_polling.is_set():
            sender()
            self._stop_polling.wait(interval)

    def _push_event(self, event: SensorEvent) -> None:
        q = self._unified_queue
        if q is None:
            return
        try:
            q.put_nowait(event)
        except (queue.Full, StateError):
            try:
                q.get_nowait()
            except queue.Empty:
                pass
            try:
                q.put_nowait(event)
            except (queue.Full, StateError):
                pass
