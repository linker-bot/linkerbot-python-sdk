import functools
import math
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Literal

import numpy as np
from scipy.spatial.transform import Rotation as R

from linkerbot.arm.a7.consts import (
    DEFAULT_POLL_INTERVALS,
    MAX_ACCELERATION,
    MAX_VELOCITY,
    MIN_ACCELERATION,
    MIN_VELOCITY,
    MOVE_L_DEFAULT_ACCELERATION,
    MOVE_L_DEFAULT_ANGULAR_ACCELERATION,
    MOVE_L_DEFAULT_MAX_ANGULAR_VELOCITY,
    MOVE_L_DEFAULT_MAX_VELOCITY,
    MOVE_L_MAX_ACCELERATION,
    MOVE_L_MAX_ANGULAR_ACCELERATION,
    MOVE_L_MAX_MAX_ANGULAR_VELOCITY,
    MOVE_L_MAX_MAX_VELOCITY,
    NUM_JOINTS,
)
from linkerbot.arm.common import ControlMode, Pose, State
from linkerbot.comm import CanInterface, CANMessageDispatcher
from linkerbot.exceptions import StateError, ValidationError
from linkerbot.motion_timer import MotionTimer

from .motor import A7Motor, SensorType


def _guard_not_moving(method):
    @functools.wraps(method)
    def wrapper(self: "A7", *args, **kwargs):
        if self.is_moving():
            raise StateError("Cannot start new motion while arm is moving.")
        return method(self, *args, **kwargs)

    return wrapper


class A7:
    def __init__(
        self,
        side: Literal["left", "right"],
        interface_name: str,
        interface_type: str = "socketcan",
        tcp_offset: list[float] = [0.0, 0.0, 0.0],
        world_frame: Literal["urdf", "maestro"] = "urdf",
    ) -> None:
        if side not in ("left", "right"):
            raise ValueError(f"side must be 'left' or 'right', got {side!r}")
        if world_frame not in ("urdf", "maestro"):
            raise ValueError(
                f"world_frame must be 'urdf' or 'maestro', got {world_frame!r}"
            )
        self._can_dispatcher = CANMessageDispatcher(
            interface_name, interface_type, on_bus_error=self._on_bus_error
        )
        self._motors = [
            A7Motor(id, self._can_dispatcher)
            for id in (range(61, 68) if side == "left" else range(51, 58))
        ]
        from linkerbot.arm.kinetix import ArmKinetix

        self._kx: ArmKinetix = ArmKinetix.from_builtin(
            "a7", side, tcp_offset=tcp_offset, world_frame=world_frame
        )
        self._control_mode: ControlMode | None = None
        self._motion_timer = MotionTimer()
        self._closed: bool = False
        self._polling: bool = False
        self._check_motors()
        for motor in self._motors:
            motor.read_initial_state()
        for motor in self._motors:
            if not motor.has_initial_data():
                raise StateError(f"Motor {motor._id} did not report initial data.")
        self.start_polling()

    def _check_motors(self) -> None:
        unresponsive = []
        for motor in self._motors:
            if not motor.check_alive():
                unresponsive.append(motor._id)
        if unresponsive:
            raise StateError(
                f"Motors {unresponsive} did not respond. "
                f"Expected {NUM_JOINTS} motors, {NUM_JOINTS - len(unresponsive)} responded. "
                f"Check wiring and power."
            )

    def _on_bus_error(self, error: Exception) -> None:
        self._bus_error = error
        self._closed = True

    @property
    def can_interface(self) -> CanInterface:
        """CAN interface this arm is bound to."""
        return self._can_dispatcher.can_interface

    def start_polling(self, intervals: dict[SensorType, float] | None = None) -> None:
        if self._polling:
            self.stop_polling()
        poll_intervals = intervals if intervals is not None else DEFAULT_POLL_INTERVALS
        for motor in self._motors:
            motor.start_polling(poll_intervals)
        self._polling = True

    def stop_polling(self) -> None:
        for motor in self._motors:
            motor.stop_polling()
        self._polling = False

    def is_moving(self) -> bool:
        return self._motion_timer.is_moving()

    def wait_motion_done(self) -> None:
        self._motion_timer.wait_done()

    def set_control_mode(self, mode: ControlMode) -> None:
        for motor in self._motors:
            motor.set_control_mode(mode)
        self._control_mode = mode

    def enable(self) -> None:
        self.reset_error()
        control_mode = (
            self._control_mode if self._control_mode is not None else ControlMode.PP
        )
        self.set_control_mode(control_mode)
        for motor in self._motors:
            motor.enable()

        time.sleep(0.1)

    def disable(self) -> None:
        for motor in self._motors:
            motor.disable()

    def reset_error(self) -> None:
        for motor in self._motors:
            motor.reset_error()

    def emergency_stop(self) -> None:
        def stop_single(motor):
            angle = motor._read_register_float(SensorType.POSITION)
            motor.set_angle(angle)

        with ThreadPoolExecutor(max_workers=len(self._motors)) as pool:
            futures = [pool.submit(stop_single, m) for m in self._motors]
            for f in as_completed(futures):
                f.result()

    def _set_angles(self, angles: list[float], *, check_limits: bool = True) -> None:
        if len(angles) != len(self._motors):
            raise ValueError(f"Angles count must be {NUM_JOINTS}, got {len(angles)}")
        if check_limits:
            for i, (angle, (lo, hi)) in enumerate(
                zip(angles, self._kx.get_joint_limits())
            ):
                if not (lo <= angle <= hi):
                    raise ValidationError(
                        f"Joint {i} angle {angle:.4f} rad out of range [{lo:.4f}, {hi:.4f}]"
                    )
        for motor, angle in zip(self._motors, angles):
            motor.set_angle(angle)

    def set_velocities(self, velocities: list[float]) -> None:
        if len(velocities) != len(self._motors):
            raise ValueError(
                f"Velocities count must be {NUM_JOINTS}, got {len(velocities)}"
            )
        for i, v in enumerate(velocities):
            if not (MIN_VELOCITY <= v <= MAX_VELOCITY):
                raise ValidationError(
                    f"Joint {i} velocity {v} out of range [{MIN_VELOCITY}, {MAX_VELOCITY}]"
                )
        for motor, velocity in zip(self._motors, velocities):
            motor.set_velocity(velocity)

    def set_accelerations(self, accelerations: list[float]) -> None:
        if len(accelerations) != len(self._motors):
            raise ValueError(
                f"Accelerations count must be {NUM_JOINTS}, got {len(accelerations)}"
            )
        for i, a in enumerate(accelerations):
            if not (MIN_ACCELERATION <= a <= MAX_ACCELERATION):
                raise ValidationError(
                    f"Joint {i} acceleration {a} out of range [{MIN_ACCELERATION}, {MAX_ACCELERATION}]"
                )
        for motor, acceleration in zip(self._motors, accelerations):
            motor.set_acceleration(acceleration)
            motor.set_deceleration(acceleration)

    def get_state(self) -> State:
        return State(
            pose=self.get_pose(),
            joint_angles=[motor.angle for motor in self._motors],
            joint_control_angles=[motor.control_angle for motor in self._motors],
            joint_velocities=[motor.velocity for motor in self._motors],
            joint_control_velocities=[motor.control_velocity for motor in self._motors],
            joint_control_acceleration=[
                motor.control_acceleration for motor in self._motors
            ],
            joint_torques=[motor.torque for motor in self._motors],
            joint_temperatures=[motor.temperature for motor in self._motors],
        )

    def get_angles(self) -> list[float]:
        return [motor.angle.angle for motor in self._motors]

    def get_control_angles(self) -> list[float]:
        return [motor.control_angle.angle for motor in self._motors]

    def get_velocities(self) -> list[float]:
        return [motor.velocity.velocity for motor in self._motors]

    def get_control_velocities(self) -> list[float]:
        return [motor.control_velocity.velocity for motor in self._motors]

    def get_control_acceleration(self) -> list[float]:
        return [motor.control_acceleration.acceleration for motor in self._motors]

    def get_torques(self) -> list[float]:
        return [motor.torque.torque for motor in self._motors]

    def get_temperatures(self) -> list[float]:
        return [motor.temperature.temperature for motor in self._motors]

    def get_pose(self) -> Pose:
        return self._kx.forward_kinematics(self.get_angles())

    def home(self, *, blocking: bool = True) -> None:
        self.move_j([0.0] * NUM_JOINTS, blocking=blocking)

    @_guard_not_moving
    def move_j(
        self,
        target_joints: list[float],
        *,
        blocking: bool = True,
    ) -> None:
        self._set_angles(target_joints)
        self._motion_timer.start(
            self._move_duration(
                self.get_angles(),
                target_joints,
                self.get_control_velocities(),
                self.get_control_acceleration(),
            )
        )
        if blocking:
            self.wait_motion_done()

    @_guard_not_moving
    def move_p(
        self,
        target_pose: Pose,
        *,
        current_angles: list[float] | None = None,
        blocking: bool = True,
    ) -> None:
        if current_angles is None:
            current_angles = self.get_angles()
        target_joints = self.inverse_kinematics(
            target_pose, current_angles=current_angles
        )
        self._set_angles(target_joints, check_limits=False)
        self._motion_timer.start(
            self._move_duration(
                self.get_angles(),
                target_joints,
                self.get_control_velocities(),
                self.get_control_acceleration(),
            )
        )
        if blocking:
            self.wait_motion_done()

    @_guard_not_moving
    def move_l(
        self,
        target_pose: Pose,
        *,
        max_velocity: float = MOVE_L_DEFAULT_MAX_VELOCITY,
        max_angular_velocity: float = MOVE_L_DEFAULT_MAX_ANGULAR_VELOCITY,
        acceleration: float = MOVE_L_DEFAULT_ACCELERATION,
        angular_acceleration: float = MOVE_L_DEFAULT_ANGULAR_ACCELERATION,
        current_pose: Pose | None = None,
        current_angles: list[float] | None = None,
    ) -> None:
        if not (0 < max_velocity <= MOVE_L_MAX_MAX_VELOCITY):
            raise ValidationError(
                f"max_velocity {max_velocity} out of range (0, {MOVE_L_MAX_MAX_VELOCITY}]"
            )
        if not (0 < max_angular_velocity <= MOVE_L_MAX_MAX_ANGULAR_VELOCITY):
            raise ValidationError(
                f"max_angular_velocity {max_angular_velocity} out of range (0, {MOVE_L_MAX_MAX_ANGULAR_VELOCITY}]"
            )
        if not (0 < acceleration <= MOVE_L_MAX_ACCELERATION):
            raise ValidationError(
                f"acceleration {acceleration} out of range (0, {MOVE_L_MAX_ACCELERATION}]"
            )
        if not (0 < angular_acceleration <= MOVE_L_MAX_ANGULAR_ACCELERATION):
            raise ValidationError(
                f"angular_acceleration {angular_acceleration} out of range (0, {MOVE_L_MAX_ANGULAR_ACCELERATION}]"
            )

        WAYPOINT_INTERVEL = 0.01

        if current_angles is not None and current_pose is not None:
            fk_pose = self._kx.forward_kinematics(current_angles)
            if not self._poses_close(fk_pose, current_pose):
                warnings.warn(
                    "current_pose does not match FK(current_angles). "
                    "Using FK result instead.",
                    stacklevel=2,
                )
                current_pose = fk_pose
        elif current_angles is not None:
            current_pose = self._kx.forward_kinematics(current_angles)
        elif current_pose is not None:
            raise ValueError(
                "current_angles must be provided when current_pose is specified."
            )
        else:
            current_angles = self.get_angles()
            current_pose = self._kx.forward_kinematics(current_angles)

        current_3d_pose = current_pose.to_list()[:3]
        target_3d_pose = target_pose.to_list()[:3]
        loc_diff = np.linalg.norm(np.array(target_3d_pose) - np.array(current_3d_pose))

        start_rot = R.from_euler(
            "zyx", [current_pose.rz, current_pose.ry, current_pose.rx]
        )
        end_rot = R.from_euler("zyx", [target_pose.rz, target_pose.ry, target_pose.rx])
        rot_diff = (start_rot.inv() * end_rot).magnitude()

        blocking_time = (
            max(
                self._trapezoidal_duration(loc_diff, max_velocity, acceleration),  # type: ignore
                self._trapezoidal_duration(
                    rot_diff, max_angular_velocity, angular_acceleration
                ),
            )
            + WAYPOINT_INTERVEL
        )
        self._motion_timer.start(blocking_time)

        current_velocities = self.get_control_velocities()
        current_accelerations = self.get_control_acceleration()

        self.set_velocities([MAX_VELOCITY] * NUM_JOINTS)
        self.set_accelerations([MAX_ACCELERATION] * NUM_JOINTS)

        send_time = time.perf_counter()
        try:
            for wp in list(
                self._kx.plan_move_l(
                    current_pose,
                    current_angles,
                    target_pose,
                    max_velocity=max_velocity,
                    acceleration=acceleration,
                    max_angular_velocity=max_angular_velocity,
                    angular_acceleration=angular_acceleration,
                    waypoint_interval=WAYPOINT_INTERVEL,
                )
            ):
                send_time += WAYPOINT_INTERVEL
                time.sleep(max(0.0, send_time - time.perf_counter()))
                self._set_angles(wp.angles, check_limits=False)
        except Exception as e:
            raise e
        finally:
            self.set_velocities(current_velocities)
            self.set_accelerations(current_accelerations)
            self.wait_motion_done()

    def set_position_kps(self, kps: list[float]) -> None:
        if len(kps) != len(self._motors):
            raise ValueError(f"KPS count must be {NUM_JOINTS}, got {len(kps)}")
        for motor, kp in zip(self._motors, kps):
            motor.set_position_kp(kp)

    def set_velocity_kps(self, kps: list[float]) -> None:
        if len(kps) != len(self._motors):
            raise ValueError(f"KPS count must be {NUM_JOINTS}, got {len(kps)}")
        for motor, kp in zip(self._motors, kps):
            motor.set_velocity_kp(kp)

    def set_velocity_kis(self, kis: list[float]) -> None:
        if len(kis) != len(self._motors):
            raise ValueError(f"KIS count must be {NUM_JOINTS}, got {len(kis)}")
        for motor, ki in zip(self._motors, kis):
            motor.set_velocity_ki(ki)

    def calibrate_zero(self) -> None:
        self.reset_error()
        for motor in self._motors:
            motor.calibrate_zero()

    def forward_kinematics(self, angles: list[float]) -> Pose:
        return self._kx.forward_kinematics(angles)

    def inverse_kinematics(
        self,
        pose: Pose,
        *,
        current_angles: list[float] | None = None,
    ) -> list[float]:
        current_angles = (
            current_angles if current_angles is not None else self.get_angles()
        )
        return self._kx.inverse_kinematics(pose, current_angles=current_angles)

    def set_joint_limits(self, limits: list[tuple[float, float]]) -> None:
        self._kx.set_joint_limits(limits)

    def get_joint_limits(self) -> list[tuple[float, float]]:
        return self._kx.get_joint_limits()

    def close(self) -> None:
        if self._closed:
            return

        self.stop_polling()
        self.wait_motion_done()
        try:
            self._can_dispatcher.stop()
        except Exception:
            pass
        self._closed = True

    def __enter__(self) -> "A7":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    @staticmethod
    def _poses_close(
        a: Pose, b: Pose, pos_tol: float = 1e-3, rot_tol: float = 1e-2
    ) -> bool:
        pos_diff = np.linalg.norm(np.array([a.x, a.y, a.z]) - np.array([b.x, b.y, b.z]))
        rot_a = R.from_euler("zyx", [a.rz, a.ry, a.rx])
        rot_b = R.from_euler("zyx", [b.rz, b.ry, b.rx])
        rot_diff = (rot_a.inv() * rot_b).magnitude()
        return bool(pos_diff < pos_tol and rot_diff < rot_tol)

    @staticmethod
    def _trapezoidal_duration(
        distance: float, speed: float, acceleration: float
    ) -> float:
        if distance < 1e-12:
            return 0.0
        v = abs(speed)
        a = abs(acceleration)
        if a < 1e-12 or v < 1e-12:
            return 0.0
        t_acc = v / a
        d_acc = 0.5 * a * t_acc**2
        if 2 * d_acc >= distance:
            return 2.0 * math.sqrt(distance / a)
        t_cruise = (distance - 2 * d_acc) / v
        return 2 * t_acc + t_cruise

    def _move_duration(
        self,
        current_angles: list[float],
        target_angles: list[float],
        control_speeds: list[float],
        control_accelerations: list[float],
    ) -> float:
        return max(
            (
                self._trapezoidal_duration(abs(tgt - cur), v, a)
                for cur, tgt, v, a in zip(
                    current_angles,
                    target_angles,
                    control_speeds,
                    control_accelerations,
                )
            ),
            default=0.0,
        )

    def save_params(self) -> None:
        for motor in self._motors:
            motor._save_params()
