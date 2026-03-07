from dataclasses import dataclass

from pydantic import BaseModel


class Pose(BaseModel):
    x: float
    y: float
    z: float
    rx: float
    ry: float
    rz: float

    @classmethod
    def from_list(cls, data: list[float]) -> "Pose":
        assert len(data) == 6, f"Expected 6 values, got {len(data)}"
        return cls(
            x=data[0],
            y=data[1],
            z=data[2],
            rx=data[3],
            ry=data[4],
            rz=data[5],
        )

    def to_list(self) -> list[float]:
        return [self.x, self.y, self.z, self.rx, self.ry, self.rz]


@dataclass
class WayPoint:
    pose: Pose
    duration: float
    angles: list[float]


class State(BaseModel):
    pose: Pose
    joint_angles: list["AngleState"]
    joint_control_angles: list["AngleState"]
    joint_velocities: list["VelocityState"]
    joint_control_velocities: list["VelocityState"]
    joint_control_acceleration: list["AccelerationState"] | None
    joint_torques: list["TorqueState"] | None
    joint_temperatures: list["TemperatureState"] | None


class AngleState(BaseModel):
    angle: float
    timestamp: float


class VelocityState(BaseModel):
    velocity: float
    timestamp: float


class AccelerationState(BaseModel):
    acceleration: float
    timestamp: float


class TorqueState(BaseModel):
    torque: float
    timestamp: float


class TemperatureState(BaseModel):
    temperature: float
    timestamp: float
