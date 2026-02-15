"""Fixtures for O6 robotic hand tests."""

import os
import time
from typing import Literal, cast

import pytest

from linkerbot import O6


@pytest.fixture(scope="module")
def o6_hand():
    """Create O6 hand instance for the test module.

    Uses environment variables for configuration:
    - CAN_INTERFACE: CAN interface name (default: "can0")
    - O6_SIDE: Hand side, "left" or "right" (default: "left")
    """
    interface = os.environ.get("CAN_INTERFACE", "can0")
    side = cast(Literal["left", "right"], os.environ.get("O6_SIDE", "left"))

    with O6(side=side, interface_name=interface) as hand:
        hand.speed.set_speeds([100.0] * 6)
        hand.acceleration.set_accelerations([100.0] * 6)
        hand.angle.set_angles([100.0] * 6)
        time.sleep(2.0)
        yield hand


def move_and_wait(hand: O6, angles: list[float], wait_sec: float = 2.0):
    """Move hand to target angles and wait for completion."""
    hand.angle.set_angles(angles)
    time.sleep(wait_sec)
