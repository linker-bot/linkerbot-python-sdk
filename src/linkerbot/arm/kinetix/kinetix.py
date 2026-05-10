import math
from collections.abc import Generator
from pathlib import Path
from typing import Literal

import numpy as np
import numpy.typing as npt
import pinocchio as pin
from pydantic import BaseModel
from scipy.optimize import least_squares, minimize
from scipy.spatial.transform import Rotation as R
from scipy.spatial.transform import Slerp

from linkerbot.arm.common import Pose, WayPoint


class IKResult(BaseModel):
    """Result of an inverse kinematics solve attempt.

    Attributes:
        joint_angles: Solved joint angles (rad).  Empty when IK fails.
        error: ``None`` on success; human-readable error string on failure.
    """

    joint_angles: list[float]
    error: str | None = None

    def is_ok(self) -> bool:
        """Return ``True`` when the solve succeeded."""
        return self.error is None


class ArmKinetix:
    """FK / IK solver and Cartesian motion planner for a robot arm.

    The kinematic chain is loaded from a user-supplied URDF file.  An
    optional TCP (Tool Centre Point) offset extends the chain beyond the
    last URDF link.  For arms whose URDFs ship with this package, see
    :meth:`from_builtin` for a convenience factory.

    Two world-frame conventions are supported:

    * ``"urdf"``    – native URDF frame (default).
    * ``"maestro"`` – 90° Z-rotation with the origin shifted to joint 2,
      matching the Maestro system.

    Args:
        urdf_path: Path to the URDF file describing the kinematic chain.
        tcp_offset: ``[x, y, z]`` translation (m) from the last URDF link
            to the actual tool centre point.
        world_frame: Coordinate-frame convention.
        side: Optional ``"left"`` / ``"right"`` tag identifying which arm
            this instance represents.  Set automatically by
            :meth:`from_builtin`; ``None`` when the side is unknown.
    """

    def __init__(
        self,
        urdf_path: str | Path,
        *,
        tcp_offset: list[float] = [0.0, 0.0, 0.0],
        world_frame: Literal["urdf", "maestro"] = "urdf",
        side: Literal["left", "right"] | None = None,
    ) -> None:
        self._urdf_path = Path(urdf_path)
        if not self._urdf_path.is_file():
            raise FileNotFoundError(f"URDF file not found: {self._urdf_path}")
        self._side: Literal["left", "right"] | None = side
        self._model = self._load_model()

        self._world_frame = world_frame
        self._rz_maestro: npt.NDArray[np.float64] = (
            np.array(  # Rz(90°) for maestro frame
                [[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]]
            )
        )
        self._perform_world_transform()
        self._tcp_offset = tcp_offset
        self._ee_frame_id = self._build_ee_frame_id()
        self._fk_data = self._model.createData()

        self._joint_limits: list[tuple[float, float]] = [
            (lower, upper)
            for lower, upper in zip(
                self._model.lowerPositionLimit.copy(),
                self._model.upperPositionLimit.copy(),
            )
        ]

    def set_joint_limits(self, limits: list[tuple[float, float]]) -> None:
        if len(limits) != len(self._joint_limits):
            raise ValueError(
                f"Expected {len(self._joint_limits)} limits, got {len(limits)}"
            )
        for i, (lower, upper) in enumerate(limits):
            if not (lower <= upper):
                raise ValueError(
                    f"Lower limit {lower} must be less than upper limit {upper}"
                )
            self._joint_limits[i] = (lower, upper)

    def get_joint_limits(self) -> list[tuple[float, float]]:
        return self._joint_limits

    @property
    def side(self) -> Literal["left", "right"] | None:
        """Side tag this instance was constructed with, or ``None``."""
        return self._side

    def _load_model(self) -> pin.Model:  # pyright: ignore[reportAttributeAccessIssue]
        """
        Load the Pinocchio model from the URDF.
        """
        return pin.buildModelFromUrdf(str(self._urdf_path))  # pyright: ignore[reportAttributeAccessIssue]

    @classmethod
    def from_builtin(
        cls,
        arm_type: Literal["a7_lite", "a7"],
        side: Literal["left", "right"],
        *,
        tcp_offset: list[float] = [0.0, 0.0, 0.0],
        world_frame: Literal["urdf", "maestro"] = "urdf",
    ) -> "ArmKinetix":
        """Construct an ArmKinetix from a URDF bundled with this package.

        Convenience factory for arms whose URDFs ship inside
        ``linkerbot.arm.kinetix.urdf``.  For arbitrary URDFs, use the
        regular constructor with a file path instead.

        Args:
            arm_type: Built-in arm identifier.
            side: ``"left"`` or ``"right"`` arm.
            tcp_offset: ``[x, y, z]`` translation (m) from the last URDF
                link to the actual tool centre point.
            world_frame: Coordinate-frame convention.
        """
        from importlib.resources import files

        path = files("linkerbot.arm.kinetix.urdf") / f"{arm_type}__{side}.urdf"
        return cls(
            urdf_path=str(path),
            tcp_offset=tcp_offset,
            world_frame=world_frame,
            side=side,
        )

    def _build_ee_frame_id(self):
        """Create and register a TCP frame in the Pinocchio model.

        The frame is placed at the last URDF link, translated by
        ``tcp_offset``.  The returned frame ID is used by FK and IK to
        query the end-effector pose and Jacobian.

        Returns:
            Pinocchio frame ID (int) of the newly added TCP frame.
        """
        last_frame = self._model.frames[self._model.nframes - 1]
        ee_placement = last_frame.placement * pin.SE3(  # pyright: ignore[reportAttributeAccessIssue]
            np.eye(3), np.array(self._tcp_offset)
        )
        ee_frame = pin.Frame(  # pyright: ignore[reportAttributeAccessIssue]
            "tcp",
            last_frame.parentJoint,
            self._model.nframes - 1,
            ee_placement,
            pin.FrameType.OP_FRAME,  # pyright: ignore[reportAttributeAccessIssue]
        )
        return self._model.addFrame(ee_frame)

    def _perform_world_transform(self) -> None:
        """Bake a world-frame transformation into the first joint placement.

        For the ``"maestro"`` convention the model is rotated 90° about Z
        and the origin is shifted to joint 2, so that all subsequent FK/IK
        results are expressed in the Maestro coordinate system.
        """
        world_transform = pin.SE3.Identity()  # pyright: ignore[reportAttributeAccessIssue]
        if self._world_frame == "maestro":
            oM2 = self._model.jointPlacements[1] * self._model.jointPlacements[2]
            p_j2 = oM2.translation.copy()
            world_transform = pin.SE3(self._rz_maestro, -self._rz_maestro @ p_j2)  # pyright: ignore[reportAttributeAccessIssue]
        self._model.jointPlacements[1] = (
            world_transform * self._model.jointPlacements[1]
        )

    def _forward_kinematics(self, angles: npt.NDArray[np.float64], data=None):
        """Low-level FK returning raw NumPy arrays.

        Args:
            angles: Joint angles (rad), shape ``(nq,)``.
            data: Pinocchio ``Data`` for thread-safe reuse.  Falls back to
                the shared ``_fk_data`` instance when ``None``.

        Returns:
            ``(pos, rot)`` – 3-D position (m) and 3×3 rotation matrix of
            the TCP, both in the configured world frame.
        """
        q = np.array(angles)
        data = self._fk_data if data is None else data
        pin.forwardKinematics(self._model, data, q)  # pyright: ignore[reportAttributeAccessIssue]
        pin.updateFramePlacements(self._model, data)  # pyright: ignore[reportAttributeAccessIssue]
        transform = data.oMf[self._ee_frame_id]
        pos: npt.NDArray[np.float64] = transform.translation.copy()
        rot: npt.NDArray[np.float64] = transform.rotation.copy()

        if self._world_frame == "maestro":
            rot = rot @ self._rz_maestro.T

        return pos, rot

    def forward_kinematics(self, angles: list[float], data=None) -> Pose:
        """Compute the TCP pose from joint angles.

        Args:
            angles: Joint angles (rad).
            data: Optional Pinocchio ``Data`` for thread-safe use.

        Returns:
            :class:`Pose` with ``(x, y, z)`` in metres and ``(rx, ry, rz)``
            as extrinsic ZYX Euler angles (rad).
        """
        pos, rot = self._forward_kinematics(np.array(angles), data)
        rotation = R.from_matrix(rot)
        rz, ry, rx = rotation.as_euler("zyx", degrees=False)
        return Pose(
            x=pos[0],
            y=pos[1],
            z=pos[2],
            rx=rx,
            ry=ry,
            rz=rz,
        )

    def inverse_kinematics_result(
        self, pose: Pose, current_angles: list[float]
    ) -> IKResult:
        """Solve IK and wrap the outcome in an :class:`IKResult`.

        Unlike :meth:`inverse_kinematics` this method never raises.
        Solver failures are captured in ``IKResult.error``.

        Args:
            pose: Desired TCP pose.
            current_angles: Joint angles (rad) used as the initial guess.

        Returns:
            :class:`IKResult` with solved angles on success, or an error
            message on failure.
        """
        try:
            joint_angles = self.inverse_kinematics(pose, current_angles=current_angles)
            return IKResult(joint_angles=joint_angles)
        except RuntimeError as e:
            return IKResult(joint_angles=[], error=str(e))

    def inverse_kinematics(
        self, pose: Pose, current_angles: list[float]
    ) -> list[float]:
        """Solve inverse kinematics for a desired TCP pose.

        Three solvers are tried in cascade until one converges:

        1. **DLS** – Damped Least-Squares with null-space joint-limit
           avoidance (iterative, fastest when near the target).
        2. **dogbox** – ``scipy.optimize.least_squares`` with box
           constraints and analytic Jacobian.
        3. **SLSQP** – ``scipy.optimize.minimize`` with analytic gradient
           (most robust fallback).

        The 6-D residual combines position error and orientation error
        (SO(3) log map).  The orientation component is scaled by
        ``ORIENT_WEIGHT`` so that position accuracy is prioritised.

        Args:
            pose: Target TCP pose (position in m, orientation as extrinsic
                ZYX Euler angles in rad).
            current_angles: Joint angles (rad) used as the initial guess.

        Returns:
            Solved joint angles (rad).

        Raises:
            RuntimeError: If all three solvers fail to converge.
        """
        data = self._model.createData()
        target_pos: npt.NDArray[np.float64] = np.array([pose.x, pose.y, pose.z])
        target_R = R.from_euler(
            "zyx", [pose.rz, pose.ry, pose.rx], degrees=False
        ).as_matrix()

        ORIENT_WEIGHT = 1.0  # down-weight orientation vs position

        def residual(q: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
            pos, rot = self._forward_kinematics(q, data)
            R_err = target_R @ rot.T
            return np.concatenate([target_pos - pos, ORIENT_WEIGHT * pin.log3(R_err)])  # pyright: ignore[reportAttributeAccessIssue]

        def jac(q: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
            pin.computeJointJacobians(self._model, data, q)  # pyright: ignore[reportAttributeAccessIssue]
            pin.updateFramePlacements(self._model, data)  # pyright: ignore[reportAttributeAccessIssue]

            J = pin.getFrameJacobian(  # pyright: ignore[reportAttributeAccessIssue]
                self._model,
                data,
                self._ee_frame_id,
                pin.ReferenceFrame.LOCAL_WORLD_ALIGNED,  # pyright: ignore[reportAttributeAccessIssue]
            )

            J_full = J.copy()
            J_full[3:, :] *= ORIENT_WEIGHT
            J_out = -J_full

            return J_out

        def objective(q: npt.NDArray[np.float64]) -> float:
            r = residual(q)
            return 0.5 * float(r @ r)

        def gradient(q: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
            r = residual(q)
            J = jac(q)
            return J.T @ r  # ∇(0.5‖r‖²) = Jᵀ r

        _ERR_TOL: float = 1e-4
        _COST_TOL: float = 0.5 * _ERR_TOL**2
        _OPT_TOL: float = 1e-15

        q0 = np.array(current_angles)
        lo = np.array([limit[0] for limit in self._joint_limits])
        hi = np.array([limit[1] for limit in self._joint_limits])

        # --- 1. DLS (Damped Least-Squares) ---
        try:
            q_dls = self._solve_dls(
                data,
                target_pos,
                target_R,
                q0,
                lo,
                hi,
                orient_weight=ORIENT_WEIGHT,
                err_tol=_ERR_TOL,
            )
            if q_dls is not None:
                return q_dls.tolist()
        except Exception:
            pass  # fall through to dogbox

        # --- 2. dogbox (least_squares) ---
        try:
            res_dogbox = least_squares(
                residual,
                q0,
                jac=jac,  # pyright: ignore[reportArgumentType]
                bounds=(lo, hi),
                method="dogbox",
                ftol=_OPT_TOL,
                xtol=_OPT_TOL,
                gtol=_OPT_TOL,
                max_nfev=100,
            )
            cost_dogbox = 0.5 * float(res_dogbox.fun @ res_dogbox.fun)
            if cost_dogbox < _COST_TOL:
                return res_dogbox.x.tolist()
        except Exception:
            pass  # fall through to SLSQP

        # --- 3. SLSQP (minimize) ---
        bounds = list(zip(lo, hi))
        res_slsqp = minimize(
            objective,
            q0,
            method="SLSQP",
            jac=gradient,
            bounds=bounds,
            options={
                "ftol": _OPT_TOL,
                "eps": _OPT_TOL,
                "maxiter": 100,
                "disp": False,
            },
        )

        if res_slsqp.fun < _COST_TOL:
            return res_slsqp.x.tolist()
        raise RuntimeError("Inverse kinematics failed to converge")

    # ------------------------------------------------------------------
    # DLS (Damped Least-Squares) solver
    # ------------------------------------------------------------------

    def _solve_dls(
        self,
        data: object,
        target_pos: npt.NDArray[np.float64],
        target_R: npt.NDArray[np.float64],
        q0: npt.NDArray[np.float64],
        lo: npt.NDArray[np.float64],
        hi: npt.NDArray[np.float64],
        *,
        orient_weight: float = 1.0,
        max_iter: int = 100,
        err_tol: float = 1e-4,
        damp: float = 1e-6,
        null_space_gain: float = 0.5,
    ) -> npt.NDArray[np.float64] | None:
        """Damped Least-Squares IK with null-space joint-limit avoidance.

        Returns the solved joint angles, or ``None`` when convergence
        was not reached within *max_iter* iterations.
        """
        q = np.clip(q0.copy(), lo, hi)

        for _ in range(max_iter):
            pin.computeJointJacobians(self._model, data, q)  # pyright: ignore[reportAttributeAccessIssue]
            pin.updateFramePlacements(self._model, data)  # pyright: ignore[reportAttributeAccessIssue]

            pos, rot = self._forward_kinematics(q, data)

            err_pos = target_pos - pos
            R_err = target_R @ rot.T
            err_orient: npt.NDArray[np.float64] = pin.log3(R_err)  # pyright: ignore[reportAttributeAccessIssue]

            if (
                np.linalg.norm(err_pos) < err_tol
                and np.linalg.norm(err_orient) < err_tol
            ):
                return q

            J: npt.NDArray[np.float64] = pin.getFrameJacobian(  # pyright: ignore[reportAttributeAccessIssue]
                self._model,
                data,
                self._ee_frame_id,
                pin.ReferenceFrame.LOCAL_WORLD_ALIGNED,  # pyright: ignore[reportAttributeAccessIssue]
            )

            J_w = J.copy()
            J_w[3:, :] *= orient_weight
            err = np.concatenate([err_pos, orient_weight * err_orient])

            JJT = J_w @ J_w.T
            J_pinv = J_w.T @ np.linalg.inv(JJT + damp * np.eye(6))
            dq = J_pinv @ err

            # Null-space joint-limit avoidance
            null_space = np.eye(self._model.nv) - J_pinv @ J_w
            limit_grad = _compute_joint_limit_gradient(q, lo, hi)
            dq += null_space_gain * (null_space @ limit_grad)

            q = pin.integrate(self._model, q, dq)  # pyright: ignore[reportAttributeAccessIssue]
            q = np.clip(q, lo, hi)

        return None  # did not converge

    @staticmethod
    def _trap_params(
        dist: float, v_max: float, a_max: float
    ) -> tuple[float, float, float, float]:
        """Compute symmetric trapezoidal velocity-profile parameters.

        If *dist* is too short to reach *v_max*, a triangular profile
        (zero cruise phase) is used instead.

        Args:
            dist: Total distance (m or rad).
            v_max: Maximum velocity.
            a_max: Maximum acceleration.

        Returns:
            ``(t_acc, v_peak, t_cruise, T)``:
            acceleration time, peak velocity reached, cruise time, and
            total motion time.
        """
        if dist < 1e-12:
            return (0.0, 0.0, 0.0, 0.0)
        t_acc = v_max / a_max
        d_acc = 0.5 * a_max * t_acc**2
        if 2 * d_acc >= dist:
            # triangular profile — can't reach v_max
            t_acc = math.sqrt(dist / a_max)
            v_peak = a_max * t_acc
            t_cruise = 0.0
        else:
            v_peak = v_max
            t_cruise = (dist - 2 * d_acc) / v_peak
        T = 2 * t_acc + t_cruise
        return (t_acc, v_peak, t_cruise, T)

    @staticmethod
    def _trap_s(
        t: float,
        t_acc: float,
        v_peak: float,
        t_cruise: float,
        a: float,
        dist: float,
    ) -> float:
        """Evaluate normalised progress along a trapezoidal profile.

        Returns a value *s* ∈ [0, 1] representing the fraction of *dist*
        covered at elapsed time *t*.  The three phases (acceleration,
        cruise, deceleration) are evaluated piece-wise.
        """
        if dist < 1e-12:
            return 1.0
        T = 2 * t_acc + t_cruise
        if t >= T:
            return 1.0
        d_acc = 0.5 * a * t_acc**2
        if t <= t_acc:
            d = 0.5 * a * t**2
        elif t <= t_acc + t_cruise:
            d = d_acc + v_peak * (t - t_acc)
        else:
            t_dec = t - t_acc - t_cruise
            d = d_acc + v_peak * t_cruise + v_peak * t_dec - 0.5 * a * t_dec**2
        return min(d / dist, 1.0)

    def plan_move_l(
        self,
        current_pose: Pose,
        current_angles: list[float],
        target_pose: Pose,
        max_velocity: float,
        acceleration: float,
        max_angular_velocity: float,
        angular_acceleration: float,
        *,
        waypoint_interval: float = 0.01,
    ) -> Generator[WayPoint, None, None]:
        """Plan a Cartesian straight-line (MoveL) trajectory.

        Generates waypoints along a linear Cartesian path from
        *current_pose* to *target_pose*.  Translation and rotation each
        follow their own trapezoidal velocity profile (independent
        velocity / acceleration limits); total motion time equals the
        slower of the two.

        Orientation is interpolated via Slerp (shortest-path rotation).
        Each intermediate pose is converted to joint space through IK,
        seeded with the previous solution for fast convergence and
        smooth joint-space motion between consecutive waypoints.

        Args:
            current_pose: Starting TCP pose.
            current_angles: Starting joint angles (rad), IK seed for the
                first waypoint.
            target_pose: Desired final TCP pose.
            max_velocity: Maximum linear velocity (m/s).
            acceleration: Linear acceleration (m/s²).
            max_angular_velocity: Maximum angular velocity (rad/s).
            angular_acceleration: Angular acceleration (rad/s²).
            waypoint_interval: Time step between waypoints (s, default 10 ms).

        Yields:
            :class:`WayPoint` with ``pose``, ``duration``, and ``angles``
            for each time step, ending exactly at *target_pose*.

        Raises:
            RuntimeError: If IK fails for any intermediate waypoint.
        """
        start_pos = np.array([current_pose.x, current_pose.y, current_pose.z])
        end_pos = np.array([target_pose.x, target_pose.y, target_pose.z])
        loc_diff = float(np.linalg.norm(end_pos - start_pos))  # position difference (m)

        start_rot = R.from_euler(
            "zyx", [current_pose.rz, current_pose.ry, current_pose.rx]
        )
        end_rot = R.from_euler("zyx", [target_pose.rz, target_pose.ry, target_pose.rx])
        rot_diff = float(
            (start_rot.inv() * end_rot).magnitude()
        )  # orientation difference (rad)

        if loc_diff < 1e-9 and rot_diff < 1e-9:
            # Start and target are essentially identical — skip planning,
            # yield the target directly with zero duration.
            yield WayPoint(pose=target_pose, duration=0.0, angles=list(current_angles))
            return

        pos_t_acc, pos_v_peak, pos_t_cruise, T_pos = self._trap_params(
            loc_diff, max_velocity, acceleration
        )
        rot_t_acc, rot_v_peak, rot_t_cruise, T_rot = self._trap_params(
            rot_diff, max_angular_velocity, angular_acceleration
        )

        T = max(T_pos, T_rot)  # slower axis dictates total time
        if T < 1e-12:
            yield WayPoint(pose=target_pose, duration=0.0, angles=list(current_angles))
            return

        slerp = (
            Slerp([0.0, 1.0], R.concatenate([start_rot, end_rot]))
            if rot_diff > 1e-9
            else None
        )

        waypoints_pose: list[Pose] = []
        t = 0.0

        while True:
            t += waypoint_interval
            if t >= T:
                break

            s_pos = self._trap_s(
                t, pos_t_acc, pos_v_peak, pos_t_cruise, acceleration, loc_diff
            )
            s_rot = self._trap_s(
                t, rot_t_acc, rot_v_peak, rot_t_cruise, angular_acceleration, rot_diff
            )

            pos = start_pos + s_pos * (end_pos - start_pos)

            if slerp is not None:
                rot = slerp(s_rot)
                rz, ry, rx = rot.as_euler("zyx")
            else:
                rx, ry, rz = current_pose.rx, current_pose.ry, current_pose.rz

            waypoints_pose.append(
                Pose(
                    x=float(pos[0]),
                    y=float(pos[1]),
                    z=float(pos[2]),
                    rx=float(rx),
                    ry=float(ry),
                    rz=float(rz),
                )
            )

        waypoints_pose.append(target_pose)  # exact target as final point

        seed = list(current_angles)

        for pose in waypoints_pose:
            ik = self.inverse_kinematics_result(pose, current_angles=seed)
            if not ik.is_ok():
                raise RuntimeError(f"plan_move_l: IK failed to converge (pose={pose})")
            seed = ik.joint_angles
            yield WayPoint(
                pose=pose, duration=waypoint_interval, angles=ik.joint_angles
            )


# ─── Module-level helpers ─────────────────────────────────────────


def _compute_joint_limit_gradient(
    q: npt.NDArray[np.float64],
    lower: npt.NDArray[np.float64],
    upper: npt.NDArray[np.float64],
    margin: float = 0.05,
) -> npt.NDArray[np.float64]:
    """Compute a gradient that pushes joints away from their limits.

    When a joint is within *margin* (fraction of its range) of a bound,
    a repulsive term is generated.  Used by DLS null-space projection.
    """
    grad = np.zeros_like(q)
    for i in range(len(q)):
        q_range = upper[i] - lower[i]
        if q_range <= 0:
            continue
        margin_abs = margin * q_range
        dist_to_lower = q[i] - lower[i]
        dist_to_upper = upper[i] - q[i]
        if dist_to_lower < margin_abs:
            grad[i] += (margin_abs - dist_to_lower) / margin_abs
        if dist_to_upper < margin_abs:
            grad[i] -= (margin_abs - dist_to_upper) / margin_abs
    return grad
