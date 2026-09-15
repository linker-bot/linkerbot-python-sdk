from __future__ import annotations

import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import pytest

from linkerbot.hand.l30 import L30, L30_JOINT_COUNT, AngleData

_DEFAULT_TIMEOUT_MS = 1000.0
_DEFAULT_SAFE_SPEED = 20
_DEFAULT_SAFE_TORQUE = 60
_DEFAULT_POLL_INTERVAL_S = 0.2


@dataclass(frozen=True, slots=True)
class L30HardwareSettings:
    library_path: Path
    node_id: int
    host_id: int
    device_index: int
    channel_index: int
    timeout_ms: float


def require_full_hardware() -> None:
    if os.environ.get("L30_HARDWARE_FULL") != "1":
        pytest.skip("Set L30_HARDWARE_FULL=1 to run L30 hardware tests")


def require_smoke_or_full_hardware() -> None:
    if (
        os.environ.get("L30_HARDWARE_SMOKE") != "1"
        and os.environ.get("L30_HARDWARE_FULL") != "1"
    ):
        pytest.skip("Set L30_HARDWARE_SMOKE=1 or L30_HARDWARE_FULL=1 to run this test")


def require_motion_allowed() -> None:
    if os.environ.get("L30_ALLOW_MOTION") != "1":
        pytest.skip("Set L30_ALLOW_MOTION=1 to run L30 write/motion hardware tests")


def hardware_settings() -> L30HardwareSettings:
    return L30HardwareSettings(
        library_path=env_path("LINKERBOT_CANFD_LIB"),
        node_id=env_int("L30_NODE_ID", 1),
        host_id=env_int("L30_HOST_ID", 0),
        device_index=env_int("L30_DEVICE_INDEX", 0),
        channel_index=env_int("L30_CHANNEL_INDEX", 0),
        timeout_ms=env_float("L30_TIMEOUT_MS", _DEFAULT_TIMEOUT_MS),
    )


@contextmanager
def open_l30(*, auto_start_periodic: bool = False) -> Iterator[L30]:
    settings = hardware_settings()
    with L30(
        node_id=settings.node_id,
        host_id=settings.host_id,
        device_index=settings.device_index,
        channel_index=settings.channel_index,
        library_path=settings.library_path,
        auto_start_periodic=auto_start_periodic,
    ) as hand:
        yield hand


def env_path(name: str) -> Path:
    value = os.environ.get(name)
    if value is None:
        pytest.skip(f"Set {name} to run L30 hardware tests")
    path = Path(value)
    if not path.exists():
        pytest.skip(f"{name} does not exist: {path}")
    return path


def env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    return int(value)


def env_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    if value is None:
        return default
    return float(value)


def safe_speed() -> int:
    return env_int("L30_SAFE_SPEED", _DEFAULT_SAFE_SPEED)


def safe_torque() -> int:
    return env_int("L30_SAFE_TORQUE", _DEFAULT_SAFE_TORQUE)


def poll_interval_s() -> float:
    return env_float("L30_POLL_INTERVAL_S", _DEFAULT_POLL_INTERVAL_S)


def safe_angles_from_env() -> list[int] | None:
    value = os.environ.get("L30_SAFE_ANGLES")
    if value is None or value.strip() == "":
        return None
    angles = [int(part.strip()) for part in value.split(",")]
    if len(angles) != L30_JOINT_COUNT:
        pytest.skip(
            f"L30_SAFE_ANGLES must contain {L30_JOINT_COUNT} comma-separated ints"
        )
    return angles


def force_all_fingers_enabled() -> bool:
    return os.environ.get("L30_FORCE_ALL_FINGERS") == "1"


def assert_joint_tuple(values: tuple[int, ...]) -> None:
    assert len(values) == L30_JOINT_COUNT


def wait_for_angle_snapshot(hand: L30, timeout_ms: float) -> AngleData:
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        snapshot = hand.angle.get_snapshot()
        if snapshot is not None:
            return snapshot
        time.sleep(0.01)
    raise AssertionError("No L30 angle snapshot received")
