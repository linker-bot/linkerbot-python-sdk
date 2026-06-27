"""Driver for the V2 motor variant used at A7V2 joints 5-6.

A7V2 mixes two motor variants on a single CAN bus:

* Joints 0-4 reuse :class:`linkerbot.arm.a7.motor.A7Motor` (CMD-byte protocol,
  PROFILE_POSITION mode, host-side polling for sensor data).
* Joints 5-6 use :class:`MotorV2` defined here. It speaks a packed-frame
  protocol with quantised parameters, runs in a Servo control mode (drive-side
  PD only — no internal trajectory generator), and emits one feedback frame
  for every command frame it receives (so polling is unnecessary, but a
  heartbeat is required to keep the drive out of fault-on-timeout).

:class:`MotorV2` mirrors :class:`A7Motor`'s public surface so that
:class:`linkerbot.arm.a7_v2.A7V2` can iterate over the mixed motor list
without ``isinstance`` branches.
"""

import logging
import threading
import time

import can

from linkerbot.arm.a7.motor import SensorType  # re-exported for parity with A7Motor
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


# Quantisation ranges. The defaults below match the V2 motor's factory
# Flash configuration for the CAN COM Theta / Velocity / Kp / Kd / Ki / Torque
# MIN-MAX parameters; if a deployment changes those Flash values, the
# constants here must be updated accordingly.
_THETA_MIN, _THETA_MAX = -12.5, +12.5  # rad
_V_MIN, _V_MAX = -10.0, +10.0  # rad/s
_KP_POS_MIN, _KP_POS_MAX = 0.0, 250.0
_KD_POS_MIN, _KD_POS_MAX = 0.0, 50.0
_KP_VEL_MIN, _KP_VEL_MAX = 0.0, 250.0
_KD_VEL_MIN, _KD_VEL_MAX = 0.0, 50.0
_KI_VEL_MIN, _KI_VEL_MAX = 0.0, 0.05
_TORQUE_MIN, _TORQUE_MAX = -50.0, +50.0

# Default PID gains carried in every Servo-mode control frame. Values are
# the manufacturer's recommended starting point; callers may override via
# set_position_kp / set_velocity_kp / set_velocity_ki.
_DEFAULT_KP_POS = 15.0
_DEFAULT_KD_POS = 4.5
_DEFAULT_KP_VEL = 50.0
_DEFAULT_KD_VEL = 0.0
_DEFAULT_KI_VEL = 0.001

# Heartbeat: re-send a no-op control frame this often to prevent the drive's
# CAN-COM watchdog (default 1 s) from firing and dropping the drive back to
# its idle state.
_HEARTBEAT_INTERVAL_S = 0.2

# State machine command suffixes. Each is an 8-byte CAN frame on the motor's
# own ID; the leading seven 0xFF bytes are an opaque prefix defined by the
# motor firmware, and the last byte selects the transition.
_ENTER_MOTOR_STATE = bytes([0xFF] * 7 + [0xFC])
_ENTER_REST_STATE = bytes([0xFF] * 7 + [0xFD])
_SET_ZERO_POSITION = bytes([0xFF] * 7 + [0xFE])

# Flash parameter R/W protocol uses a separate CAN ID space:
# arbitration_id = 0x600 + motor_id. This avoids collisions with the runtime
# command/feedback traffic on the same wire.
_FLASH_REQUEST_ID_BASE = 0x600
_FLASH_FRAME_HEADER = 0x67
_FLASH_FRAME_FOOTER = 0x76
_FLASH_CMD_READ = 0x04
_FLASH_CMD_WRITE = 0x15
_FLASH_INDEX_SAVE = 0x00
_FLASH_INDEX_CONTROL_MODE = 0x0B

# Feedback frame status byte values. Only 0x00..0x05 are valid.
_STATUS_REST = 0x00
_STATUS_VALID = {0x00, 0x01, 0x02, 0x03, 0x04, 0x05}


def _quantize(value: float, vmin: float, vmax: float, bits: int) -> int:
    max_raw = (1 << bits) - 1
    clamped = max(vmin, min(vmax, value))
    normalized = (clamped - vmin) / (vmax - vmin)
    return int(round(normalized * max_raw))


def _dequantize(raw: int, vmin: float, vmax: float, bits: int) -> float:
    max_raw = (1 << bits) - 1
    return vmin + (raw / max_raw) * (vmax - vmin)


class MotorV2:
    """Driver for the V2 motor variant in its Servo control mode.

    Designed to be ducktype-compatible with
    :class:`linkerbot.arm.a7.motor.A7Motor`: same method names, same property
    surface, same lifecycle. :class:`linkerbot.arm.a7_v2.A7V2` mixes five
    :class:`A7Motor` (joints 0-4) and two :class:`MotorV2` (joints 5-6) into
    a single ``_motors`` list and treats them uniformly.

    Internal differences from A7Motor:

    - **No drive-side trajectory generator.** Every ``set_angle`` is the
      drive's instantaneous PD target. Smooth motion requires the host to
      stream interpolated waypoints — :meth:`A7V2.move_j` / :meth:`A7V2.move_l`
      do this.
    - **State machine has only Rest / Motor states** (no continuous
      "enabled flag"). Transitions are via the fixed 8-byte commands
      ``_ENTER_MOTOR_STATE`` / ``_ENTER_REST_STATE`` / ``_SET_ZERO_POSITION``.
    - **Heartbeat required.** The drive auto-reverts to Rest after its
      CAN-COM watchdog (default 1 s) fires. A background thread re-sends
      a no-op Servo frame every 200 ms.
    - **Sensor data arrives unsolicited** via feedback frames (one per
      received command frame on the same ID). No polling needed.

    Parameters
    ----------
    id : int
        Motor CAN ID (51-67 per A7V2 wiring).
    dispatcher : CANMessageDispatcher
        Shared CAN bus dispatcher.
    """

    def __init__(self, id: int, dispatcher: CANMessageDispatcher) -> None:
        self._id = id
        self._dispatcher = dispatcher

        # Sensor state (populated by feedback frames)
        self._angle: AngleState
        self._velocity: VelocityState
        self._torque: TorqueState
        self._temperature: TemperatureState
        self._fault_code: int = 0

        # Control state (cached host-side; the V2 drive does not expose its
        # own "configured" target values via standard runtime frames).
        self._enabled: bool = False
        self._control_angle: AngleState
        self._control_velocity: VelocityState
        self._control_acceleration: AccelerationState
        self._position_kp: float = _DEFAULT_KP_POS
        self._position_kd: float = _DEFAULT_KD_POS
        self._velocity_kp: float = _DEFAULT_KP_VEL
        self._velocity_kd: float = _DEFAULT_KD_VEL
        self._velocity_ki: float = _DEFAULT_KI_VEL

        # Flash protocol responses (ID = 0x600 + motor_id)
        self._flash_relay: DataRelay[bytes] = DataRelay()

        # Heartbeat thread
        self._heartbeat_thread: threading.Thread | None = None
        self._stop_event = threading.Event()

        self._dispatcher.subscribe(self._on_message)

    # ------------------------------------------------------------------ #
    # Properties (mirror A7Motor's surface)
    # ------------------------------------------------------------------ #

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

    @property
    def fault_code(self) -> int:
        return self._fault_code

    # ------------------------------------------------------------------ #
    # Frame I/O
    # ------------------------------------------------------------------ #

    def _send_control(self, data: bytes) -> None:
        msg = can.Message(
            arbitration_id=self._id,
            data=data,
            is_extended_id=False,
        )
        self._dispatcher.send(msg)

    def _send_flash(self, data: bytes) -> None:
        msg = can.Message(
            arbitration_id=_FLASH_REQUEST_ID_BASE + self._id,
            data=data,
            is_extended_id=False,
        )
        self._dispatcher.send(msg)

    def _build_servo_frame(self, theta_ref: float, v_ref: float) -> bytes:
        """Build an 8-byte Servo-mode control frame.

        Layout: theta_ref 16-bit BE, v_ref 8-bit, then four 8-bit gains
        (position Kp, position Kd, velocity Kp, velocity Kd) and finally
        velocity Ki. Every parameter is linearly quantised against the
        configured MIN/MAX range; see module-level ``_*_MIN`` / ``_*_MAX``.
        """
        theta_q = _quantize(theta_ref, _THETA_MIN, _THETA_MAX, 16)
        v_q = _quantize(v_ref, _V_MIN, _V_MAX, 8)
        kp_pos_q = _quantize(self._position_kp, _KP_POS_MIN, _KP_POS_MAX, 8)
        kd_pos_q = _quantize(self._position_kd, _KD_POS_MIN, _KD_POS_MAX, 8)
        kp_vel_q = _quantize(self._velocity_kp, _KP_VEL_MIN, _KP_VEL_MAX, 8)
        kd_vel_q = _quantize(self._velocity_kd, _KD_VEL_MIN, _KD_VEL_MAX, 8)
        ki_vel_q = _quantize(self._velocity_ki, _KI_VEL_MIN, _KI_VEL_MAX, 8)
        return bytes([
            (theta_q >> 8) & 0xFF,
            theta_q & 0xFF,
            v_q,
            kp_pos_q,
            kd_pos_q,
            kp_vel_q,
            kd_vel_q,
            ki_vel_q,
        ])

    def _on_message(self, msg: can.Message) -> None:
        if msg.arbitration_id == self._id:
            self._on_feedback_frame(bytes(msg.data))
        elif msg.arbitration_id == _FLASH_REQUEST_ID_BASE + self._id:
            self._on_flash_response(bytes(msg.data))

    def _on_feedback_frame(self, data: bytes) -> None:
        """Decode an 8-byte feedback frame.

        Layout: status 8-bit, position 16-bit BE, velocity 12-bit BE,
        torque 12-bit BE, fault 8-bit, temperature 8-bit.

        The status byte is one of {0x00..0x05}; frames with any other
        first byte are dropped (they could only be an echo of our own
        outbound command frame and not a real feedback).
        """
        if len(data) < 8:
            return
        status = data[0]
        if status not in _STATUS_VALID:
            return

        now = time.time()
        self._enabled = status != _STATUS_REST

        pos_raw = (data[1] << 8) | data[2]
        vel_raw = (data[3] << 4) | (data[4] >> 4)
        torque_raw = ((data[4] & 0x0F) << 8) | data[5]
        fault = data[6]
        temp = data[7]

        self._angle = AngleState(
            angle=_dequantize(pos_raw, _THETA_MIN, _THETA_MAX, 16),
            timestamp=now,
        )
        self._velocity = VelocityState(
            velocity=_dequantize(vel_raw, _V_MIN, _V_MAX, 12),
            timestamp=now,
        )
        self._torque = TorqueState(
            torque=_dequantize(torque_raw, _TORQUE_MIN, _TORQUE_MAX, 12),
            timestamp=now,
        )
        self._temperature = TemperatureState(temperature=float(temp), timestamp=now)
        self._fault_code = fault

    def _on_flash_response(self, data: bytes) -> None:
        # Response layout: <motor_id> <index> <D0> <D1> <D2> <D3> 0x00 0xFF
        if len(data) < 8:
            return
        if data[0] != (self._id & 0xFF):
            return
        self._flash_relay.push(bytes(data[2:6]))

    # ------------------------------------------------------------------ #
    # State machine
    # ------------------------------------------------------------------ #

    def set_control_mode(self, mode: ControlMode) -> None:
        """No-op for the V2 motor; control mode is Flash-persisted, not
        runtime-switchable per frame.

        A7V2 calls this with ``ControlMode.PP`` before enable. We accept PP
        as the placeholder that maps onto this motor's Servo mode (already
        configured in Flash by the factory and verified at init via
        :meth:`check_alive`).
        """
        if mode != ControlMode.PP:
            raise ValueError(
                f"MotorV2 only accepts ControlMode.PP (mapped to Servo); got {mode!r}"
            )

    def enable(self) -> None:
        # Sync control_angle to the current measured angle so the heartbeat
        # holds position rather than jumping to a stale target left over
        # from a prior session.
        if hasattr(self, "_angle"):
            self._control_angle = AngleState(
                angle=self._angle.angle, timestamp=time.time()
            )
        self._send_control(_ENTER_MOTOR_STATE)
        self._enabled = True

    def disable(self) -> None:
        self._send_control(_ENTER_REST_STATE)
        self._enabled = False

    def reset_error(self) -> None:
        # Soft faults clear by transitioning Motor → Rest. Non-clearable
        # hardware faults (codes ≥ 128) require a power cycle; we silently
        # do nothing for them (reading ``fault_code`` lets callers detect
        # this).
        self._send_control(_ENTER_REST_STATE)

    def calibrate_zero(self) -> None:
        self._send_control(_SET_ZERO_POSITION)
        self._save_params()

    # ------------------------------------------------------------------ #
    # Control (cached, applied on the next set_angle Servo frame)
    # ------------------------------------------------------------------ #

    def set_angle(self, angle: float) -> None:
        self._control_angle = AngleState(angle=angle, timestamp=time.time())
        v_ref = (
            self._control_velocity.velocity
            if hasattr(self, "_control_velocity")
            else 0.0
        )
        self._send_control(self._build_servo_frame(angle, v_ref))

    def set_velocity(self, velocity: float) -> None:
        # Cached as V_ref for the next Servo control frame.
        self._control_velocity = VelocityState(
            velocity=velocity, timestamp=time.time()
        )

    def set_acceleration(self, acceleration: float) -> None:
        # Servo mode has no drive-side acceleration limit; cache for callers
        # that read back ``control_acceleration``. The host-side trajectory
        # layer in :meth:`A7V2.move_j` is what actually shapes the motion
        # ramp.
        self._control_acceleration = AccelerationState(
            acceleration=acceleration, timestamp=time.time()
        )

    def set_deceleration(self, deceleration: float) -> None:
        # Servo mode has no drive-side deceleration; intentional no-op.
        # ``A7V2.set_accelerations`` calls both ``set_acceleration`` and
        # ``set_deceleration`` on every motor for parity with A7.
        pass

    def set_position_kp(self, kp: float) -> None:
        self._position_kp = kp

    def set_velocity_kp(self, kp: float) -> None:
        self._velocity_kp = kp

    def set_velocity_ki(self, ki: float) -> None:
        self._velocity_ki = ki

    # ------------------------------------------------------------------ #
    # Init / lifecycle
    # ------------------------------------------------------------------ #

    def check_alive(self, timeout_s: float = 0.1) -> bool:
        """Read the Control Mode Flash parameter and verify it is Servo (1).

        Read-only, no motion. Returns True if the motor responds and reports
        Servo mode. If it responds but the mode is something else, returns
        True with a warning (so A7V2 init still succeeds, but callers are
        notified that the drive is misconfigured).
        """
        try:
            data = self._read_flash_param(_FLASH_INDEX_CONTROL_MODE, timeout_s)
        except TimeoutError:
            return False
        mode_value = int.from_bytes(data[:4], "little", signed=True)
        if mode_value != 1:
            logger.warning(
                "Motor %d Flash Control Mode = %d, expected 1 (Servo). "
                "MotorV2 only supports Servo mode.",
                self._id,
                mode_value,
            )
        return True

    def read_initial_state(self, timeout_s: float = 1.0) -> None:
        # Sending Enter Rest State on motor_id is safe (no motion either
        # way) and triggers exactly one feedback frame which populates
        # angle / velocity / torque / temperature / enabled.
        self._send_control(_ENTER_REST_STATE)

        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if hasattr(self, "_angle"):
                break
            time.sleep(0.005)
        else:
            raise TimeoutError(
                f"Motor {self._id} did not return feedback within {timeout_s}s"
            )

        # Initialise the cached control state from the current angle so the
        # heartbeat holds position with V_ref = 0 (rigid hold) until the
        # host commands otherwise.
        now = time.time()
        self._control_angle = AngleState(angle=self._angle.angle, timestamp=now)
        self._control_velocity = VelocityState(velocity=0.0, timestamp=now)
        # Acceleration is host-side only; pick a conservative default to
        # match A7lite's defaults so ``A7V2.set_accelerations`` validation
        # passes if callers query before setting.
        self._control_acceleration = AccelerationState(
            acceleration=10.0, timestamp=now
        )

    def has_initial_data(self) -> bool:
        return all(
            hasattr(self, attr)
            for attr in (
                "_angle",
                "_velocity",
                "_torque",
                "_temperature",
                "_control_angle",
                "_control_velocity",
                "_control_acceleration",
            )
        )

    # ------------------------------------------------------------------ #
    # Polling = heartbeat
    # ------------------------------------------------------------------ #

    def start_polling(
        self, intervals: dict[SensorType, float] | None = None
    ) -> None:
        """Start the heartbeat thread.

        ``intervals`` is accepted for parity with
        :meth:`A7Motor.start_polling` but ignored — this motor does not need
        polling. Feedback frames arrive automatically from each control
        frame; the heartbeat thread simply keeps that frame flow alive while
        the host is idle.
        """
        del intervals  # unused; kept for interface compatibility
        if self._heartbeat_thread is not None and self._heartbeat_thread.is_alive():
            return
        self._stop_event.clear()
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            daemon=True,
            name=f"MotorV2.heartbeat_{self._id}",
        )
        self._heartbeat_thread.start()

    def stop_polling(self) -> None:
        self._stop_event.set()
        if self._heartbeat_thread is not None:
            self._heartbeat_thread.join(timeout=2.0)
            self._heartbeat_thread = None

    def _heartbeat_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                if hasattr(self, "_control_angle"):
                    # V_ref = 0 means "hold this angle" (rigid hold via PD).
                    frame = self._build_servo_frame(
                        self._control_angle.angle, v_ref=0.0
                    )
                    self._send_control(frame)
            except Exception:
                logger.exception("Heartbeat error on motor %d", self._id)
            self._stop_event.wait(_HEARTBEAT_INTERVAL_S)

    # ------------------------------------------------------------------ #
    # Flash parameter R/W (ID = 0x600 + motor_id)
    # ------------------------------------------------------------------ #

    def _read_flash_param(self, index: int, timeout_s: float = 1.0) -> bytes:
        request = bytes([
            _FLASH_FRAME_HEADER, index & 0xFF,
            0x00, 0x00, 0x00, 0x00,
            _FLASH_CMD_READ, _FLASH_FRAME_FOOTER,
        ])
        self._send_flash(request)
        return self._flash_relay.wait(timeout_s)

    def _write_flash_param(self, index: int, data: bytes) -> None:
        if len(data) != 4:
            raise ValueError(f"Flash param data must be 4 bytes, got {len(data)}")
        request = (
            bytes([_FLASH_FRAME_HEADER, index & 0xFF])
            + data
            + bytes([_FLASH_CMD_WRITE, _FLASH_FRAME_FOOTER])
        )
        self._send_flash(request)

    def _save_params(self) -> None:
        # Save Flash uses Index = 0; the data payload is ignored.
        self._write_flash_param(_FLASH_INDEX_SAVE, bytes(4))
        # Flash erase+write may take 1-2 s; the drive is briefly
        # unresponsive during the operation, so we sleep conservatively.
        time.sleep(1.0)
