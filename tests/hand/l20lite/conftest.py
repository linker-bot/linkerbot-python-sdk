"""Fixtures for L20Lite robotic hand tests."""

import os
import time
from typing import Literal, cast

import pytest

from linkerbot import L20lite


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
        # hand.speed.set_speeds([100.0] * 10)
        hand.angle.set_angles([100.0] * 10)
        time.sleep(3.0)
        yield hand


def move_and_wait(hand: L20lite, angles: list[float], wait_sec: float = 2.0):
    """Move hand to target angles and wait for completion."""
    hand.angle.set_angles(angles)
    time.sleep(wait_sec)
