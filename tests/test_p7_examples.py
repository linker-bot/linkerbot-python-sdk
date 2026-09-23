from __future__ import annotations

import importlib.util
import math
import os
import subprocess
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DETECT_SCRIPT = REPO_ROOT / "examples" / "p7_detect.sh"
MOVE_EXAMPLE = REPO_ROOT / "examples" / "p7_enable_small_move.py"


def _load_move_example() -> ModuleType:
    spec = importlib.util.spec_from_file_location("p7_enable_small_move", MOVE_EXAMPLE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_command(path: Path, body: str) -> None:
    path.write_text(f"#!/bin/sh\n{body}", encoding="utf-8")
    path.chmod(0o755)


def _run_detector(
    tmp_path: Path, *, missing_first_motor: bool
) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    send_log = tmp_path / "cansend.log"
    _write_command(
        bin_dir / "ip",
        """if [ "$1" = "-details" ]; then
    printf '%s\n' '2: can0: <NOARP,UP,LOWER_UP,ECHO> mtu 16 state UP'
    printf '%s\n' '    link/can'
    printf '%s\n' '    can state ERROR-ACTIVE bitrate 1000000'
else
    printf '%s\n' '2: can0: <NOARP,UP,LOWER_UP,ECHO> mtu 16 state UP'
fi
""",
    )
    _write_command(
        bin_dir / "cansend",
        """printf '%s\n' "$*" >> "$P7_SEND_LOG"
""",
    )
    response_lines = [
        "(0.000000) can0 03D#01  TX - -",
        "(0.000000) can0 03E#01  TX - -",
        "(0.000000) can0 03F#01  TX - -",
        "(0.000000) can0 040#01  TX - -",
        "(0.000000) can0 041#01  TX - -",
        "(0.000002) can0 03E#0101  RX - -",
        "(0.000003) can0 03F#0101  RX - -",
        "(0.000004) can0 040#0101  RX - -",
        "(0.000005) can0 041#0101  RX - -",
        "(0.000006) can0 642#420B0100000000FF  RX - -",
        "(0.000007) can0 643#430B0100000000FF  RX - -",
    ]
    if not missing_first_motor:
        response_lines.append("(0.000001) can0 03D#0101  RX - -")
    candump_body = "\n".join(f"printf '%s\\n' '{line}'" for line in response_lines)
    _write_command(bin_dir / "candump", f"{candump_body}\nsleep 0.1\n")

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["P7_SEND_LOG"] = str(send_log)
    result = subprocess.run(
        ["bash", str(DETECT_SCRIPT), "--side", "left", "--interface", "can0"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        timeout=5,
    )
    assert send_log.read_text(encoding="utf-8").splitlines() == [
        "can0 03D#01",
        "can0 03E#01",
        "can0 03F#01",
        "can0 040#01",
        "can0 041#01",
        "can0 642#670B000000000476",
        "can0 643#670B000000000476",
    ]
    return result


def test_p7_detector_reports_complete_arm(tmp_path: Path) -> None:
    result = _run_detector(tmp_path, missing_first_motor=False)

    assert result.returncode == 0, result.stderr
    assert "P7 detected: all 7 motors responded." in result.stdout


def test_p7_detector_reports_missing_motor(tmp_path: Path) -> None:
    result = _run_detector(tmp_path, missing_first_motor=True)

    assert result.returncode == 1
    assert "joint 1: motor 61" in result.stdout
    assert "Incomplete P7: 6/7 motors responded." in result.stderr


def test_choose_offset_target_uses_larger_limit_margin() -> None:
    example = _load_move_example()

    assert example.choose_offset_target(0.0, -1.0, 2.0, 0.1) == pytest.approx(0.1)
    assert example.choose_offset_target(1.9, -1.0, 2.0, 0.1) == pytest.approx(1.8)


def test_small_move_returns_to_start_and_disables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    example = _load_move_example()
    events: list[object] = []
    moves: list[list[float]] = []
    start_angles = [0.0] * 7

    class FakeP7:
        def __init__(self, **kwargs: str) -> None:
            events.append(("init", kwargs))

        def get_angles(self) -> list[float]:
            return start_angles.copy()

        def get_joint_limits(self) -> list[tuple[float, float]]:
            return [(-1.0, 1.0)] * 7

        def get_control_velocities(self) -> list[float]:
            return [0.5] * 7

        def get_control_acceleration(self) -> list[float]:
            return [2.0] * 7

        def set_velocities(self, values: list[float]) -> None:
            events.append(("velocities", values.copy()))

        def set_accelerations(self, values: list[float]) -> None:
            events.append(("accelerations", values.copy()))

        def enable(self) -> None:
            events.append("enable")

        def move_j(self, values: list[float]) -> None:
            moves.append(values.copy())
            events.append(("move", values.copy()))

        def emergency_stop(self) -> None:
            events.append("emergency_stop")

        def disable(self) -> None:
            events.append("disable")

        def close(self) -> None:
            events.append("close")

    monkeypatch.setattr(example, "P7", FakeP7)
    monkeypatch.setattr(example.time, "sleep", lambda _seconds: None)
    args = example.parse_args(
        [
            "--side",
            "left",
            "--interface",
            "can0",
            "--joint",
            "1",
            "--delta-degrees",
            "3",
            "--yes",
        ]
    )

    example.run(args)

    assert len(moves) == 2
    assert moves[0][0] == pytest.approx(math.radians(3.0))
    assert moves[1] == start_angles
    assert "emergency_stop" not in events
    assert events[-2:] == ["disable", "close"]


def test_small_move_failure_stops_disables_and_closes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    example = _load_move_example()
    events: list[str] = []

    class FailingP7:
        def __init__(self, **_kwargs: str) -> None:
            pass

        def get_angles(self) -> list[float]:
            return [0.0] * 7

        def get_joint_limits(self) -> list[tuple[float, float]]:
            return [(-1.0, 1.0)] * 7

        def get_control_velocities(self) -> list[float]:
            return [0.5] * 7

        def get_control_acceleration(self) -> list[float]:
            return [2.0] * 7

        def set_velocities(self, _values: list[float]) -> None:
            pass

        def set_accelerations(self, _values: list[float]) -> None:
            pass

        def enable(self) -> None:
            events.append("enable")

        def move_j(self, _values: list[float]) -> None:
            events.append("move")
            raise RuntimeError("simulated motion failure")

        def emergency_stop(self) -> None:
            events.append("emergency_stop")

        def disable(self) -> None:
            events.append("disable")

        def close(self) -> None:
            events.append("close")

    monkeypatch.setattr(example, "P7", FailingP7)
    monkeypatch.setattr(example.time, "sleep", lambda _seconds: None)
    args = example.parse_args(["--side", "right", "--yes"])

    with pytest.raises(RuntimeError, match="simulated motion failure"):
        example.run(args)

    assert events == ["enable", "move", "emergency_stop", "disable", "close"]
