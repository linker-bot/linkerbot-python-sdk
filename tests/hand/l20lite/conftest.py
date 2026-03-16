"""Fixtures for L20Lite robotic hand tests."""

import os
import time
from typing import Literal, cast

import pytest

from linkerbot import L20lite

L20LITE_TEST_ORDER: dict[str, int] = {
    "test_validation": 1,
    "test_lifecycle": 2,
    "test_fault": 3,
    "test_error_handling": 4,
    "test_polling": 5,
    "test_streaming": 6,
    "test_version": 7,
    "test_temperature": 8,
    "test_angle": 9,
    "test_speed": 10,
    "test_torque": 11,
    "test_force_sensor": 12,
    "test_stress": 13,
}


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Reorder l20lite tests: validation -> lifecycle -> ... -> stress."""
    indexed: list[tuple[pytest.Item, tuple[int, int, int]]] = []
    for idx, item in enumerate(items):
        path_str = str(item.path)
        if "hand/l20lite" not in path_str or "conftest" in path_str:
            indexed.append((item, (0, idx, 0)))
        else:
            stem = item.path.stem
            rank = L20LITE_TEST_ORDER.get(stem)
            if rank is not None:
                indexed.append((item, (1, rank, 0)))
            else:
                indexed.append((item, (0, idx, 0)))

    indexed.sort(key=lambda x: x[1])
    items[:] = [i for i, _ in indexed]


@pytest.fixture(scope="module")
def l20lite_hand():
    """Create L20lite hand instance for the test module.

    Uses environment variables for configuration:
    - CAN_INTERFACE: CAN interface name (default: "can0")
    - L20LITE_SIDE: Hand side, "left" or "right" (default: "left")
    """
    interface = os.environ.get("CAN_INTERFACE", "can0")
    side = cast(Literal["left", "right"], os.environ.get("L20LITE_SIDE", "left"))

    with L20lite(side=side, interface_name=interface) as hand:
        hand.speed.set_speeds([100.0] * 10)
        hand.angle.set_angles([100.0] * 10)
        time.sleep(2.0)
        yield hand


@pytest.fixture(scope="session")
def closed_hand():
    """Create a closed L20lite hand instance for post-close tests."""
    interface = os.environ.get("CAN_INTERFACE", "can0")
    side = cast(Literal["left", "right"], os.environ.get("L20LITE_SIDE", "left"))

    with L20lite(side=side, interface_name=interface) as hand:
        pass
    return hand


def move_and_wait(hand: L20lite, angles: list[float], wait_sec: float = 2.0) -> None:
    """Move hand to target angles and wait for completion."""
    hand.angle.set_angles(angles)
    time.sleep(wait_sec)


def move_and_print(hand: L20lite, angles: list[float], wait_sec: float = 2.0):
    """Move hand to target angles, wait, then print current angles."""
    hand.angle.set_angles(angles)
    time.sleep(wait_sec)
    data = hand.angle.get_blocking(timeout_ms=500)
    print(f"\n  Current angles: {[f'{a:.1f}' for a in data.angles.to_list()]}")
    return data
