"""Fixtures for L25 robotic hand tests."""

import os
import time
from typing import Literal, cast

import pytest

from linkerbot import L25


@pytest.fixture(scope="module")
def l25_hand():
    """Create L25 hand instance for the test module.

    Uses environment variables for configuration:
    - CAN_INTERFACE: CAN interface name (default: "can0")
    - L25_SIDE: Hand side, "left" or "right" (default: "left")
    """
    interface = os.environ.get("CAN_INTERFACE", "can0")
    side = cast(Literal["left", "right"], os.environ.get("L25_SIDE", "left"))

    with L25(side=side, interface_name=interface) as hand:
        hand.angle.set_angles([100.0] * 16)
        time.sleep(3.0)
        yield hand


def move_and_wait(hand: L25, angles: list[float], wait_sec: float = 2.0):
    """Move hand to target angles and wait for completion."""
    hand.angle.set_angles(angles)
    time.sleep(wait_sec)
