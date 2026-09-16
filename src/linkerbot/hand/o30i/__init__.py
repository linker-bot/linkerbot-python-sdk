"""Compatibility wrapper for :mod:`linkerbot.hand.o30`.

Use the renamed ``o30`` package for new code.
"""

import sys
from importlib import import_module

_target = import_module("linkerbot.hand.o30")
for _name in getattr(_target, "__all__", ()):
    globals()[_name] = getattr(_target, _name)

_module_aliases = {"o30i": "o30"}
for _module in (
    "acceleration",
    "angle",
    "current",
    "diagnostics",
    "events",
    "fault",
    "joints",
    "motion_time",
    "o30i",
    "o30",
    "protocol",
    "sensor",
    "speed",
    "temperature",
    "torque",
    "version",
    "voltage",
    "_runtime",
):
    sys.modules[f"{__name__}.{_module}"] = import_module(
        f"linkerbot.hand.o30.{_module_aliases.get(_module, _module)}"
    )

__all__ = list(getattr(_target, "__all__", ()))
