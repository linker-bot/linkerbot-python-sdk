"""Fixtures for L6 robotic hand tests."""

import os
import time
from typing import Literal, cast

import pytest

from linkerbot import L6


@pytest.fixture(scope="module")
def l6_hand():
    """Create L6 hand instance for the test module.

    Uses environment variables for configuration:
    - CAN_INTERFACE: CAN interface name (default: "can0")
    - L6_SIDE: Hand side, "left" or "right" (default: "left")
    """
    interface = os.environ.get("CAN_INTERFACE", "can0")
    side = cast(Literal["left", "right"], os.environ.get("L6_SIDE", "left"))

    with L6(side=side, interface_name=interface) as hand:
        hand.speed.set_speeds([100.0] * 6)
        hand.angle.set_angles([100.0] * 6)
        time.sleep(1.0)
        yield hand


def move_and_wait(hand: L6, angles: list[float], wait_sec: float = 1.0):
    """Move hand to target angles and wait for completion."""
    hand.angle.set_angles(angles)
    time.sleep(wait_sec)
