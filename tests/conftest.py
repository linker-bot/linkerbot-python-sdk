"""Shared fixtures and interactive test framework for linkerhand tests."""

import json
import os
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, cast

import pytest

from linkerbot import L6


@dataclass
class StepResult:
    """Result of a single interactive test step."""

    instruction: str
    expected: str
    passed: bool | None = None
    notes: str = ""


@dataclass
class PendingStep:
    """A step waiting to be executed."""

    instruction: str
    action: Callable[[], Any]
    expected: str


class InteractiveSession:
    """Interactive test session for human verification.

    Usage:
        session = InteractiveSession("test_name")
        session.step(
            instruction="Moving thumb to 0%",
            action=lambda: hand.angle.set_angles([0.0, ...]),
            expected="Thumb should be fully extended",
        )
        session.step(...)
        session.run()  # Execute all steps with human verification
        session.save_report()

        if session.failed_steps():
            pytest.fail("Test failed")
    """

    def __init__(self, test_name: str) -> None:
        self.test_name = test_name
        self.tester: str = ""
        self.timestamp: str = datetime.now().isoformat()
        self._pending_steps: list[PendingStep] = []
        self._results: list[StepResult] = []

    def step(
        self,
        instruction: str,
        action: Callable[[], Any],
        expected: str,
    ) -> "InteractiveSession":
        """Add a test step.

        Args:
            instruction: Description of what will happen (shown before action).
            action: Callback to execute (e.g., move the hand).
            expected: What the user should observe after action completes.

        Returns:
            Self for method chaining.
        """
        self._pending_steps.append(
            PendingStep(instruction=instruction, action=action, expected=expected)
        )
        return self

    def run(self) -> "InteractiveSession":
        """Execute all steps with human verification.

        For each step:
        1. Print instruction
        2. Execute action callback
        3. Ask if result matches expected
        4. Allow user to add notes (empty = no notes)
        """
        print(f"\n{'=' * 60}")
        print(f"Interactive Test: {self.test_name}")
        print(f"{'=' * 60}")

        self.tester = input("Tester name: ").strip()
        total = len(self._pending_steps)

        for i, step in enumerate(self._pending_steps, 1):
            print(f"\n--- Step {i}/{total} ---")
            print(f"Action: {step.instruction}")

            input("Press Enter to execute...")

            # Execute the action
            step.action()

            print(f"Expected: {step.expected}")
            result = input("Result correct? (y/n/s to skip): ").lower().strip()

            passed: bool | None
            if result == "s":
                passed = None
            else:
                passed = result == "y"

            notes = input("Notes (Enter to skip): ").strip()

            self._results.append(
                StepResult(
                    instruction=step.instruction,
                    expected=step.expected,
                    passed=passed,
                    notes=notes,
                )
            )

        self._pending_steps.clear()
        return self

    def save_report(self, report_dir: Path | None = None) -> Path:
        """Save test result as JSON report."""
        if report_dir is None:
            report_dir = Path(__file__).parent / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{self.test_name}_{datetime.now():%Y%m%d_%H%M%S}.json"
        filepath = report_dir / filename

        report_data = {
            "test_name": self.test_name,
            "tester": self.tester,
            "timestamp": self.timestamp,
            "steps": [asdict(r) for r in self._results],
            "summary": {
                "total": len(self._results),
                "passed": sum(1 for r in self._results if r.passed is True),
                "failed": sum(1 for r in self._results if r.passed is False),
                "skipped": sum(1 for r in self._results if r.passed is None),
            },
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)

        print(f"\nReport saved: {filepath}")
        return filepath

    def failed_steps(self) -> list[StepResult]:
        """Return list of failed steps."""
        return [r for r in self._results if r.passed is False]

    @property
    def results(self) -> list[StepResult]:
        """Get all step results."""
        return self._results.copy()


@pytest.fixture(scope="module")
def l6_hand():
    """Create L6 hand instance for the test module.

    Uses environment variables for configuration:
    - CAN_INTERFACE: CAN interface name (default: "can0")
    - L6_SIDE: Hand side, "left" or "right" (default: "left")
    """
    interface = os.environ.get("CAN_INTERFACE", "can0")
    side = cast(Literal["left", "right"], os.environ.get("L6_SIDE", "left"))

    with L6(side=side, interface_name=interface) as hand:
        yield hand


@pytest.fixture
def interactive_session(request) -> InteractiveSession:
    """Create interactive test session for human verification."""
    return InteractiveSession(test_name=request.node.name)
