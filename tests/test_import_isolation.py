"""Import-isolation regression tests.

These tests guard the contract that the linkerbot package's subpackages stay
runtime-isolated:

* ``import linkerbot`` does not eagerly load ``linkerbot.arm`` or
  ``linkerbot.hand`` (both are lazy via PEP 562 ``__getattr__``).
* ``from linkerbot import <arm name>`` only loads the arm subtree; ``hand``
  and any hand-specific dependency (e.g. ``tomli_w``) stays out of
  ``sys.modules``.
* ``from linkerbot import <hand name>`` only loads the hand subtree.
* ``import linkerbot.hand.angle_mapping`` does not load ``tomli_w``; it is
  only needed when the mapping is actually persisted to disk.

Each scenario runs in a fresh subprocess so that one test's ``sys.modules``
side effects cannot mask a regression in another. Same-process inspection of
``sys.modules`` is unreliable here because pytest, conftest, fixtures, and
prior tests may have already imported half the tree.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap

import pytest


def _run_isolated(script: str) -> str:
    """Run ``script`` in a clean Python subprocess and return its stdout."""
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(script)],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


@pytest.mark.basic
def test_import_linkerbot_does_not_load_arm_or_hand() -> None:
    output = _run_isolated(
        """
        import sys
        import linkerbot  # noqa: F401

        loaded = sorted(m for m in sys.modules if m.startswith("linkerbot."))
        assert "linkerbot.arm" not in sys.modules, (
            f"linkerbot.arm leaked into sys.modules; subtree={loaded}"
        )
        assert "linkerbot.hand" not in sys.modules, (
            f"linkerbot.hand leaked into sys.modules; subtree={loaded}"
        )
        print("OK")
        """
    )
    assert output == "OK"


@pytest.mark.basic
def test_arm_public_name_does_not_load_hand_or_tomli_w() -> None:
    output = _run_isolated(
        """
        import sys
        from linkerbot import A7lite  # noqa: F401

        assert "linkerbot.arm" in sys.modules
        assert "linkerbot.hand" not in sys.modules, (
            "loading an arm public name must not pull in the hand subtree"
        )
        assert "tomli_w" not in sys.modules, (
            "tomli_w is a hand-only dependency and must not be loaded for arm users"
        )
        print("OK")
        """
    )
    assert output == "OK"


@pytest.mark.basic
def test_hand_public_name_does_not_load_arm_or_tomli_w() -> None:
    output = _run_isolated(
        """
        import sys
        from linkerbot import L6  # noqa: F401

        assert "linkerbot.hand" in sys.modules
        assert "linkerbot.arm" not in sys.modules, (
            "loading a hand public name must not pull in the arm subtree"
        )
        assert "tomli_w" not in sys.modules, (
            "tomli_w must remain unloaded until a mapping is persisted"
        )
        print("OK")
        """
    )
    assert output == "OK"


@pytest.mark.basic
def test_import_linkerbot_hand_does_not_load_each_model() -> None:
    output = _run_isolated(
        """
        import sys
        import linkerbot.hand  # noqa: F401

        eager_loaded = [
            m for m in sys.modules
            if m.startswith("linkerbot.hand.") and m.count(".") == 2
        ]
        assert eager_loaded == [], (
            f"linkerbot.hand must not eagerly load any model module, "
            f"found: {sorted(eager_loaded)}"
        )
        print("OK")
        """
    )
    assert output == "OK"


@pytest.mark.basic
def test_import_angle_mapping_does_not_load_tomli_w() -> None:
    output = _run_isolated(
        """
        import sys
        from linkerbot.hand.angle_mapping import AngleMappingManager  # noqa: F401

        assert "tomli_w" not in sys.modules, (
            "tomli_w must be deferred to _save_file and not pulled in by import"
        )
        print("OK")
        """
    )
    assert output == "OK"
