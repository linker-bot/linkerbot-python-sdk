"""Regression tests for pytest angle-mapping configuration isolation."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_wide_scope_fixtures_do_not_touch_user_config(tmp_path: Path) -> None:
    user_config = tmp_path / "user-config"
    sentinel = user_config / "linkerbot" / "hand_angle_mappings.toml"
    sentinel.parent.mkdir(parents=True)
    sentinel.write_text("sentinel = 'unchanged'\n", encoding="utf-8")
    before = sentinel.stat()

    suite = tmp_path / "nested-suite"
    suite.mkdir()
    (suite / "conftest.py").write_text(
        "pytest_plugins = ('tests.conftest',)\n",
        encoding="utf-8",
    )
    (suite / "test_scopes.py").write_text(
        """
import os
from pathlib import Path

import pytest

from linkerbot.hand.angle_mapping import AngleMappingManager

setup_order = []


@pytest.fixture(scope="session")
def session_hand(isolate_hand_config):
    setup_order.append("session")
    manager = AngleMappingManager("session", ["joint"])
    assert manager.path.is_relative_to(isolate_hand_config)
    return manager


@pytest.fixture(scope="module")
def module_hand(isolate_hand_config):
    setup_order.append("module")
    manager = AngleMappingManager("module", ["joint"])
    assert manager.path.is_relative_to(isolate_hand_config)
    return manager


def test_wide_scopes_see_isolation_first(session_hand, module_hand):
    config_root = Path(os.environ["XDG_CONFIG_HOME"])
    assert session_hand.path.is_relative_to(config_root)
    assert module_hand.path.is_relative_to(config_root)
    assert setup_order == ["session", "module"]
""".lstrip(),
        encoding="utf-8",
    )

    environment = os.environ.copy()
    environment["XDG_CONFIG_HOME"] = str(user_config)
    environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", str(suite)],
        cwd=Path(__file__).resolve().parents[2],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert sentinel.read_text(encoding="utf-8") == "sentinel = 'unchanged'\n"
    after = sentinel.stat()
    assert after.st_mtime_ns == before.st_mtime_ns
    assert after.st_size == before.st_size
