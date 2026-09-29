"""Compatibility wrapper for :mod:`linkerbot.hand.l20`.

Use the renamed ``l20`` package for new code.
"""

import sys
from importlib import import_module

_target = import_module("linkerbot.hand.l20")
for _name in getattr(_target, "__all__", ()):
    globals()[_name] = getattr(_target, _name)

_module_aliases = {"l25": "l20"}
for _module in (
    "angle",
    "events",
    "fault",
    "force_sensor",
    "speed",
    "temperature",
    "torque",
    "version",
    "l25",
    "l20",
):
    sys.modules[f"{__name__}.{_module}"] = import_module(
        f"linkerbot.hand.l20.{_module_aliases.get(_module, _module)}"
    )

__all__ = list(getattr(_target, "__all__", ()))
