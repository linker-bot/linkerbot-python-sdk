import logging
import struct
import threading
import time
from enum import Enum, IntEnum

import can

from linkerbot.arm.common import ControlMode
from linkerbot.arm.common.model import (
    AccelerationState,
    AngleState,
    TemperatureState,
    TorqueState,
    VelocityState,
)
from linkerbot.comm import CANMessageDispatcher
from linkerbot.exceptions import TimeoutError
from linkerbot.relay import DataRelay

logger = logging.getLogger(__name__)


class SensorType(IntEnum):
    """Sensor types that support background polling."""

    POSITION = 0x06
    TORQUE = 0x03
    VELOCITY = 0x05
    TEMPERATURE = 0x5F


class InternalSensorType(IntEnum):
    ENABLED = 0x2B
    ACCELERATION = 0x1D
    POSITION_KP = 0x19
    VELOCITY_KP = 0x17
    VELOCITY_KI = 0x18
    HANDSHAKE = 0x01


class _ControlModeValue(int, Enum):
    PP = 0x05


_CONTROL_MODE_MAP = {
    ControlMode.PP: _ControlModeValue.PP,
}


class A7Motor:
    def __init__(self, id: int, dispatcher: CANMessageDispatcher) -> None:
        self._id = id
        self._dispatcher = dispatcher

        # Sensor state (populated by polling)
        self._angle: AngleState
        self._velocity: VelocityState
        self._torque: TorqueState
        self._temperature: TemperatureState

        # Control state (read at init, updated on set)
        self._enabled: bool
        self._control_angle: AngleState
        self._control_velocity: VelocityState
        self._control_acceleration: AccelerationState
        self._position_kp: float
        self._velocity_kp: float
        self._velocity_ki: float

        # One DataRelay per read command byte
        self._read_relays: dict[int, DataRelay[bytes]] = {}

        # Polling
        self._poll_threads: list[threading.Thread] = []
        self._stop_event = threading.Event()

        self._dispatcher.subscribe(self._on_message)

    @property
    def angle(self) -> AngleState:
        return self._angle

    @property
    def velocity(self) -> VelocityState:
        return self._velocity

    @property
    def torque(self) -> TorqueState:
        return self._torque

    @property
    def temperature(self) -> TemperatureState:
        return self._temperature

    @property
    def control_angle(self) -> AngleState:
        return self._control_angle

    @property
    def control_velocity(self) -> VelocityState:
        return self._control_velocity

    @property
    def control_acceleration(self) -> AccelerationState:
        return self._control_acceleration

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def position_kp(self) -> float:
        return self._position_kp

    @property
    def velocity_kp(self) -> float:
        return self._velocity_kp

    @property
    def velocity_ki(self) -> float:
        return self._velocity_ki

    def _send(self, data: bytes) -> None:
        msg = can.Message(
            arbitration_id=self._id,
            data=data,
            is_extended_id=False,
        )
        self._dispatcher.send(msg)

    def _on_message(self, msg: can.Message) -> None:
        if msg.arbitration_id != self._id:
            return
        if not msg.data:
            return
        cmd = msg.data[0]
        relay = self._read_relays.get(cmd)
        if relay is not None:
            relay.push(bytes(msg.data[1:]))

    def _get_relay(self, cmd: int) -> DataRelay[bytes]:
        relay = self._read_relays.get(cmd)
        if relay is None:
            relay = DataRelay()
            self._read_relays[cmd] = relay
        return relay

    def _read_register(self, cmd: int, timeout_s: float = 1.0) -> bytes:
        relay = self._get_relay(cmd)
        self._send(bytes([cmd]))
        return relay.wait(timeout_s)

    def _read_register_float(self, cmd: int, timeout_s: float = 1.0) -> float:
        data = self._read_register(cmd, timeout_s)
        return struct.unpack("<f", data[:4])[0]

    def _save_params(self) -> None:
        self._send(bytes([0x0D]))
        time.sleep(0.001)

    def set_control_mode(self, mode: ControlMode) -> None:
        mode_byte = _CONTROL_MODE_MAP[mode]
        self._send(bytes([0x07, mode_byte]))

    def enable(self) -> None:
        self._enabled = True
        self._send(bytes([0x2A, 0x01]))

    def disable(self) -> None:
        self._enabled = False
        self._send(bytes([0x2A, 0x00]))

    def calibrate_zero(self) -> None:
        self._send(bytes([0x87]))
        self._save_params()

    def reset_error(self) -> None:
        self._send(bytes([0xFE]))

    def set_angle(self, angle: float) -> None:
        self._control_angle = AngleState(angle=angle, timestamp=time.time())
        self._send(bytes([0x0A]) + struct.pack("<f", angle))

    def set_velocity(self, velocity: float) -> None:
        self._control_velocity = VelocityState(velocity=velocity, timestamp=time.time())
        self._send(bytes([0x1F]) + struct.pack("<f", velocity))

    def set_acceleration(self, acceleration: float) -> None:
        self._control_acceleration = AccelerationState(
            acceleration=acceleration, timestamp=time.time()
        )
        self._send(bytes([0x20]) + struct.pack("<f", acceleration))

    def set_deceleration(self, deceleration: float) -> None:
        self._send(bytes([0x21]) + struct.pack("<f", deceleration))

    def set_velocity_kp(self, kp: float) -> None:
        self._velocity_kp = kp
        self._send(bytes([0x10]) + struct.pack("<f", kp))

    def set_velocity_ki(self, ki: float) -> None:
        self._velocity_ki = ki
        self._send(bytes([0x11]) + struct.pack("<f", ki))

    def set_position_kp(self, kp: float) -> None:
        self._position_kp = kp
        self._send(bytes([0x12]) + struct.pack("<f", kp))

    def read_initial_state(self, timeout_s: float = 1.0) -> None:
        now = time.time()
        self._angle = AngleState(
            angle=self._read_register_float(SensorType.POSITION, timeout_s),
            timestamp=now,
        )
        self._velocity = VelocityState(
            velocity=self._read_register_float(SensorType.VELOCITY, timeout_s),
            timestamp=now,
        )
        self._torque = TorqueState(
            torque=self._read_register_float(SensorType.TORQUE, timeout_s),
            timestamp=now,
        )
        self._temperature = TemperatureState(
            temperature=self._read_register_float(SensorType.TEMPERATURE, timeout_s),
            timestamp=now,
        )
        self._enabled = bool(
            self._read_register(InternalSensorType.ENABLED, timeout_s)[0]
        )
        self._control_angle = AngleState(
            angle=self._read_register_float(SensorType.POSITION, timeout_s),
            timestamp=now,
        )
        self._control_velocity = VelocityState(
            velocity=self._read_register_float(SensorType.VELOCITY, timeout_s),
            timestamp=now,
        )
        self._control_acceleration = AccelerationState(
            acceleration=self._read_register_float(
                InternalSensorType.ACCELERATION, timeout_s
            ),
            timestamp=now,
        )
        self._position_kp = self._read_register_float(
            InternalSensorType.POSITION_KP, timeout_s
        )
        self._velocity_kp = self._read_register_float(
            InternalSensorType.VELOCITY_KP, timeout_s
        )
        self._velocity_ki = self._read_register_float(
            InternalSensorType.VELOCITY_KI, timeout_s
        )

    def has_initial_data(self) -> bool:
        return all(
            hasattr(self, a)
            for a in (
                "_angle",
                "_velocity",
                "_torque",
                "_temperature",
                "_enabled",
                "_control_angle",
                "_control_velocity",
                "_control_acceleration",
                "_position_kp",
                "_velocity_kp",
                "_velocity_ki",
            )
        )

    def check_alive(self, timeout_s: float = 0.02) -> bool:
        try:
            self._read_register(InternalSensorType.HANDSHAKE, timeout_s)
            return True
        except TimeoutError:
            return False

    def start_polling(self, intervals: dict[SensorType, float]) -> None:
        self._stop_event.clear()
        for sensor_type, interval_s in intervals.items():
            thread = threading.Thread(
                target=self._poll_sensor,
                args=(sensor_type, interval_s),
                daemon=True,
                name=f"LensMotor.poll_{sensor_type.name.lower()}",
            )
            self._poll_threads.append(thread)
            thread.start()

    def stop_polling(self) -> None:
        self._stop_event.set()
        for thread in self._poll_threads:
            thread.join(timeout=2.0)
        self._poll_threads.clear()

    def _poll_sensor(self, sensor_type: SensorType, interval_s: float) -> None:
        cmd = int(sensor_type)
        relay = self._get_relay(cmd)
        while not self._stop_event.is_set():
            try:
                self._send(bytes([cmd]))
                data = relay.wait(timeout_s=interval_s)
                value = struct.unpack("<f", data[:4])[0]
                now = time.time()
                match sensor_type:
                    case SensorType.POSITION:
                        self._angle = AngleState(angle=value, timestamp=now)
                    case SensorType.VELOCITY:
                        self._velocity = VelocityState(velocity=value, timestamp=now)
                    case SensorType.TORQUE:
                        self._torque = TorqueState(torque=value, timestamp=now)
                    case SensorType.TEMPERATURE:
                        self._temperature = TemperatureState(
                            temperature=value, timestamp=now
                        )
            except TimeoutError:
                logger.debug(
                    "Poll timeout for %s on motor %d", sensor_type.name, self._id
                )
            except Exception:
                logger.exception(
                    "Poll error for %s on motor %d", sensor_type.name, self._id
                )
            self._stop_event.wait(interval_s)
