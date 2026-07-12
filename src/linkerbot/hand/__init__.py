"""Lazy re-exports for the hand subpackage.

Each hand model is loaded on first attribute access via PEP 562
``__getattr__`` so that ``import linkerbot.hand`` (or ``from linkerbot.hand
import L6``) does not force every other model — and every dependency that
those models pull in transitively, like ``tomli_w`` for ``angle_mapping`` —
to load.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - import-time only for static checkers
    from .l6 import L6
    from .l20lite import L20lite
    from .l25 import L25
    from .l30 import L30, L30Bus
    from .o6 import O6
    from .o20 import O20
    from .o30i import O30i

_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "L6": ("linkerbot.hand.l6", "L6"),
    "L20lite": ("linkerbot.hand.l20lite", "L20lite"),
    "L25": ("linkerbot.hand.l25", "L25"),
    "L30": ("linkerbot.hand.l30", "L30"),
    "L30Bus": ("linkerbot.hand.l30", "L30Bus"),
    "O6": ("linkerbot.hand.o6", "O6"),
    "O20": ("linkerbot.hand.o20", "O20"),
    "O30i": ("linkerbot.hand.o30i", "O30i"),
}


def __getattr__(name: str) -> Any:
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module 'linkerbot.hand' has no attribute {name!r}")
    module_name, attr = target
    value = getattr(importlib.import_module(module_name), attr)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted({*globals(), *_LAZY_EXPORTS})


__all__ = ["L6", "O6", "L20lite", "L25", "L30", "L30Bus", "O20", "O30i"]
