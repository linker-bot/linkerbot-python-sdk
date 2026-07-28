"""Linkerhand Python SDK for dexterous hand and robotic arm control.

Public names from the ``arm`` and ``hand`` subpackages are exposed lazily via
PEP 562 ``__getattr__``: the underlying submodule is imported on first
attribute access, so users that only need the arm SDK do not pay the cost of
loading the hand SDK (and its dependencies) and vice versa.

``CanInterface`` and the exception types are imported eagerly because they have
no heavy or optional dependencies and are shared by both subpackages.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any

from .comm import CanInterface
from .exceptions import (
    CANError,
    LinkerbotError,
    StateError,
    TimeoutError,
    ValidationError,
)

if TYPE_CHECKING:  # pragma: no cover - import-time only for static checkers
    from .arm import A7, P7, A7lite, ControlMode, Pose
    from .hand import L6, L25, L30, O6, O20, L20lite, L30Bus, O30i

# Map every lazily-exported public name to (submodule, attribute).
# Adding a new public re-export here is the only change required to surface it
# at the top level without forcing eager import of its subpackage.
_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "A7": ("linkerbot.arm", "A7"),
    "P7": ("linkerbot.arm", "P7"),
    "A7lite": ("linkerbot.arm", "A7lite"),
    "ControlMode": ("linkerbot.arm", "ControlMode"),
    "Pose": ("linkerbot.arm", "Pose"),
    "L6": ("linkerbot.hand", "L6"),
    "L20lite": ("linkerbot.hand", "L20lite"),
    "L25": ("linkerbot.hand", "L25"),
    "L30": ("linkerbot.hand", "L30"),
    "L30Bus": ("linkerbot.hand", "L30Bus"),
    "O6": ("linkerbot.hand", "O6"),
    "O20": ("linkerbot.hand", "O20"),
    "O30i": ("linkerbot.hand", "O30i"),
}


def __getattr__(name: str) -> Any:
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module 'linkerbot' has no attribute {name!r}")
    module_name, attr = target
    value = getattr(importlib.import_module(module_name), attr)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted({*globals(), *_LAZY_EXPORTS})


__all__ = [
    "LinkerbotError",
    "TimeoutError",
    "CANError",
    "ValidationError",
    "StateError",
    "L6",
    "L20lite",
    "O6",
    "L25",
    "L30",
    "L30Bus",
    "O20",
    "O30i",
    "A7",
    "P7",
    "A7lite",
    "Pose",
    "ControlMode",
    "CanInterface",
]
