import functools
import math
import time
import warnings
from typing import Literal

import numpy as np
from scipy.spatial.transform import Rotation as R

from linkerbot.arm.a7_lite.consts import (
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
)
from linkerbot.arm.common import ControlMode, Pose, State
from linkerbot.comm import CanInterface, CANMessageDispatcher
from linkerbot.exceptions import StateError, ValidationError
from linkerbot.motion_timer import MotionTimer

from .motor import A7liteMotor


def _guard_not_moving(method):
    @functools.wraps(method)
    def wrapper(self: "A7lite", *args, **kwargs):
        if self.is_moving():
            raise StateError("Cannot start new motion while arm is moving.")
        return method(self, *args, **kwargs)

    return wrapper


class A7lite:
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
            A7liteMotor(id, self._can_dispatcher)
            for id in (range(61, 68) if side == "left" else range(51, 58))
        ]
        from linkerbot.arm.kinetix import ArmKinetix

        self._kx: ArmKinetix = ArmKinetix.from_builtin(
            "a7_lite", side, tcp_offset=tcp_offset, world_frame=world_frame
        )
        self._control_mode: ControlMode | None = None
        self._motion_timer = MotionTimer()
        self._closed: bool = False
        self._check_motors()
        for motor in self._motors:
            motor.start_reporting()
            motor.read_initial_state()
        self._wait_reporting_data()

    def _wait_reporting_data(self, timeout_s: float = 1.0) -> None:
        """Wait for all motors to receive reporting data.

        Polls until every motor has received at least one reporting
        frame (angle, velocity, torque, temperature), or raises
        StateError on timeout.
        """
        deadline = time.perf_counter() + timeout_s
        while time.perf_counter() < deadline:
            if all(motor.has_reporting_data() for motor in self._motors):
                return
            time.sleep(0.01)

        missing = [m._id for m in self._motors if not m.has_reporting_data()]
        raise StateError(
            f"Motors {missing} did not report data within {timeout_s}s. "
            f"Check that reporting is enabled and CAN bus is healthy."
        )

    def _check_motors(self) -> None:
        """Verify all 7 motors respond on the CAN bus.

        Always checks ALL motors regardless of individual failures,
        then raises StateError listing every unresponsive motor ID.
        """
        unresponsive = []
        for motor in self._motors:
            if not motor.check_alive():
                unresponsive.append(motor._id)

        if unresponsive:
            raise StateError(
                f"Motors {unresponsive} did not respond. "
                f"Expected 7 motors, {7 - len(unresponsive)} responded. "
                f"Check wiring and power."
            )

    def _on_bus_error(self, error: Exception) -> None:
        self._bus_error = error
        self._closed = True

    @property
    def can_interface(self) -> CanInterface:
        """CAN interface this arm is bound to."""
        return self._can_dispatcher.can_interface

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

        time.sleep(0.1)  # wait 0.1s for motor to report

    def disable(self) -> None:
        for motor in self._motors:
            motor.disable()

    # def get_error(self) -> A7liteError: ...

    def reset_error(self) -> None:
        for motor in self._motors:
            motor.reset_error()

    def emergency_stop(self) -> None:
        saved_velocities = self.get_control_velocities()
        self.set_velocities([0.0] * 7)
        time.sleep(2.0)
        self.set_velocities(saved_velocities)

    def _set_angles(self, angles: list[float], *, check_limits: bool = True) -> None:
        if len(angles) != len(self._motors):
            raise ValueError(f"Angles count must be 7, got {len(angles)}")
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
            raise ValueError(f"Velocities count must be 7, got {len(velocities)}")
        for i, v in enumerate(velocities):
            if not (MIN_VELOCITY <= v <= MAX_VELOCITY):
                raise ValidationError(
                    f"Joint {i} velocity {v} out of range [{MIN_VELOCITY}, {MAX_VELOCITY}]"
                )
        for motor, velocity in zip(self._motors, velocities):
            motor.set_velocity(velocity)

    def set_accelerations(self, accelerations: list[float]) -> None:
        if len(accelerations) != len(self._motors):
            raise ValueError(f"Accelerations count must be 7, got {len(accelerations)}")
        for i, a in enumerate(accelerations):
            if not (MIN_ACCELERATION <= a <= MAX_ACCELERATION):
                raise ValidationError(
                    f"Joint {i} acceleration {a} out of range [{MIN_ACCELERATION}, {MAX_ACCELERATION}]"
                )
        for motor, acceleration in zip(self._motors, accelerations):
            motor.set_acceleration(acceleration)

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

    def home(
        self,
        *,
        blocking: bool = True,
    ) -> None:
        """Move all joints to zero position.

        Args:
            blocking: If True, block until motion completes.
        """
        self.move_j([0.0] * 7, blocking=blocking)

    @_guard_not_moving
    def move_j(
        self,
        target_joints: list[float],
        *,
        blocking: bool = True,
    ) -> None:
        """Move to target joint angles using the motor's built-in profile.

        Sends the target angles directly to each motor and estimates the
        total duration via per-joint trapezoidal profiles.

        Args:
            target_joints: Target angles (rad) for all 7 joints.
            blocking: If True, block until motion completes.
        """
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
        """Move to target pose (point-to-point).

        Solves IK for the target pose, then delegates to move_j.
        The end-effector path is NOT guaranteed to be a straight line.

        Args:
            target_pose: Desired end-effector pose (position in m, orientation in rad).
            current_angles: Current joint angles (rad) for IK seeding;
                read from motors if None.
            blocking: If True, block until motion completes.
        """
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
        """Move the end-effector along a straight line in Cartesian space.

        Waypoints are generated by ArmKinetix.plan_move_l (trapezoidal velocity
        profile + Slerp orientation interpolation) and streamed to the motors
        at a fixed interval (10 ms). Motor velocity/acceleration limits are
        temporarily raised to MAX so that each waypoint is reached before the
        next one arrives.

        Args:
            target_pose: Desired end-effector pose (position in m, orientation in rad).
            max_velocity: Peak translational velocity (m/s).
            max_angular_velocity: Peak angular velocity (rad/s).
            acceleration: Translational acceleration (m/s^2).
            angular_acceleration: Angular acceleration (rad/s^2).
            current_pose: Starting pose (position in m, orientation in rad);
                read from motors if None.
            current_angles: Starting joint angles (rad); read from motors if None.
        """
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

        WAYPOINT_INTERVEL = 0.01  # waypoint streaming period (s)

        # Resolve current_angles and current_pose with consistency check.
        #   angles + pose  -> verify FK(angles) ≈ pose; warn & override pose if not
        #   angles only    -> compute pose from FK
        #   pose only      -> error (angles are required for IK seeding)
        #   neither        -> read angles from motors, then compute pose
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

        # --- Compute translational and rotational distances ---
        current_3d_pose = current_pose.to_list()[:3]
        target_3d_pose = target_pose.to_list()[:3]
        loc_diff = np.linalg.norm(np.array(target_3d_pose) - np.array(current_3d_pose))

        start_rot = R.from_euler(
            "zyx", [current_pose.rz, current_pose.ry, current_pose.rx]
        )
        end_rot = R.from_euler("zyx", [target_pose.rz, target_pose.ry, target_pose.rx])
        rot_diff = (
            start_rot.inv() * end_rot
        ).magnitude()  # orientation difference (rad)

        # Total duration is the longer of the two trapezoidal profiles
        blocking_time = (
            max(
                self._trapezoidal_duration(
                    loc_diff,  # type: ignore
                    max_velocity,
                    acceleration,
                ),
                self._trapezoidal_duration(
                    rot_diff,
                    max_angular_velocity,
                    angular_acceleration,
                ),
            )
            + WAYPOINT_INTERVEL
        )  # add one interval to ensure the last waypoint is reached
        self._motion_timer.start(blocking_time)

        # Save current motor limits, then raise to MAX so motors can track
        # the streamed waypoints without being clamped by the default limits.
        current_velocities = self.get_control_velocities()
        current_accelerations = self.get_control_acceleration()

        self.set_velocities([MAX_VELOCITY] * 7)
        self.set_accelerations([MAX_ACCELERATION] * 7)

        # Stream waypoints to motors at a fixed interval (soft real-time).
        # send_time tracks the ideal wall-clock time for each send to
        # compensate for loop jitter.
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
            # Restore original motor limits regardless of success or failure
            self.set_velocities(current_velocities)
            self.set_accelerations(current_accelerations)
            self.wait_motion_done()

    @staticmethod
    def _poses_close(
        a: Pose, b: Pose, pos_tol: float = 1e-3, rot_tol: float = 1e-2
    ) -> bool:
        """Check whether two poses are approximately equal.

        Args:
            a, b: Poses to compare.
            pos_tol: Position tolerance in meters (default 1 mm).
            rot_tol: Orientation tolerance in radians (default ~0.57°).
        """
        pos_diff = np.linalg.norm(np.array([a.x, a.y, a.z]) - np.array([b.x, b.y, b.z]))
        rot_a = R.from_euler("zyx", [a.rz, a.ry, a.rx])
        rot_b = R.from_euler("zyx", [b.rz, b.ry, b.rx])
        rot_diff = (rot_a.inv() * rot_b).magnitude()
        return bool(pos_diff < pos_tol and rot_diff < rot_tol)

    @staticmethod
    def _trapezoidal_duration(
        distance: float, speed: float, acceleration: float
    ) -> float:
        """Compute trapezoidal-profile duration for a single axis.

        Args:
            distance: Total travel distance (m or rad).
            speed: Maximum velocity (m/s or rad/s).
            acceleration: Acceleration (m/s² or rad/s²).

        Returns:
            Motion duration (s).
        """
        if distance < 1e-12:
            return 0.0
        v = abs(speed)
        a = abs(acceleration)
        if a < 1e-12 or v < 1e-12:
            return 0.0
        t_acc = v / a
        d_acc = 0.5 * a * t_acc**2
        if 2 * d_acc >= distance:
            # Triangular profile
            return 2.0 * math.sqrt(distance / a)
        # Full trapezoidal profile
        t_cruise = (distance - 2 * d_acc) / v
        return 2 * t_acc + t_cruise

    def _move_duration(
        self,
        current_angles: list[float],
        target_angles: list[float],
        control_speeds: list[float],
        control_accelerations: list[float],
    ) -> float:
        """Compute the maximum trapezoidal-profile duration across all joints.

        Args:
            current_angles: Current joint angles (rad).
            target_angles: Target joint angles (rad).
            control_speeds: Per-joint velocity limits (rad/s).
            control_accelerations: Per-joint acceleration limits (rad/s²).

        Returns:
            Duration (s) of the slowest joint.
        """
        return max(
            (
                self._trapezoidal_duration(abs(tgt - cur), v, a)
                for cur, tgt, v, a in zip(
                    current_angles, target_angles, control_speeds, control_accelerations
                )
            ),
            default=0.0,
        )

    def forward_kinematics(self, angles: list[float]) -> Pose:
        """Compute the TCP pose from joint angles.

        Args:
            angles: Joint angles (rad).

        Returns:
            :class:`Pose` (position in m, orientation in rad).
        """
        return self._kx.forward_kinematics(angles)

    def inverse_kinematics(
        self,
        pose: Pose,
        *,
        current_angles: list[float] | None = None,
    ) -> list[float]:
        """Solve IK for a desired TCP pose.

        Args:
            pose: Target TCP pose (position in m, orientation in rad).
            current_angles: Joint angles (rad) as IK seed;
                read from motors if None.

        Returns:
            Solved joint angles (rad).
        """
        current_angles = (
            current_angles if current_angles is not None else self.get_angles()
        )
        return self._kx.inverse_kinematics(pose, current_angles=current_angles)

    def calibrate_zero(self) -> None:
        self.reset_error()
        for motor in self._motors:
            motor.calibrate_zero()

    def set_position_kps(self, kps: list[float]) -> None:
        if len(kps) != len(self._motors):
            raise ValueError(f"KPS count must be 7, got {len(kps)}")
        for motor, kp in zip(self._motors, kps):
            motor.set_position_kp(kp)

    def set_velocity_kps(self, kps: list[float]) -> None:
        if len(kps) != len(self._motors):
            raise ValueError(f"KPS count must be 7, got {len(kps)}")
        for motor, kp in zip(self._motors, kps):
            motor.set_velocity_kp(kp)

    def set_velocity_kis(self, kis: list[float]) -> None:
        if len(kis) != len(self._motors):
            raise ValueError(f"KIS count must be 7, got {len(kis)}")
        for motor, ki in zip(self._motors, kis):
            motor.set_velicity_ki(ki)

    def set_velocity_filt_gains(self, gains: list[float]) -> None:
        if len(gains) != len(self._motors):
            raise ValueError(f"Gains count must be 7, got {len(gains)}")
        for motor, gain in zip(self._motors, gains):
            motor.set_velocity_filt_gain(gain)

    def close(self) -> None:
        if self._closed:
            return

        self.wait_motion_done()
        try:
            self._can_dispatcher.stop()
        except Exception:
            pass
        self._closed = True

    def set_joint_limits(self, limits: list[tuple[float, float]]) -> None:
        self._kx.set_joint_limits(limits)

    def get_joint_limits(self) -> list[tuple[float, float]]:
        return self._kx.get_joint_limits()

    def __enter__(self) -> "A7lite":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
