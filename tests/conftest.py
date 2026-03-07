"""Shared fixtures and interactive test framework for linkerhand tests."""

import json
import os
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest


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
        self.tester: str = os.environ.get("TESTER", "")
        self._started_at: datetime = datetime.now()
        self._pending_steps: list[PendingStep] = []
        self._results: list[StepResult] = []
        self._quit_early: bool = False

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

        if not self.tester:
            self.tester = input("Tester name: ").strip()
        else:
            print(f"Tester: {self.tester}")

        total = len(self._pending_steps)

        for i, step in enumerate(self._pending_steps, 1):
            print(f"\n--- Step {i}/{total} ---")
            print(f"Action: {step.instruction}")

            input("Press Enter to execute...")

            # Execute the action
            step.action()

            print(f"Expected: {step.expected}")
            result = input("Result correct? (y/n/s/q): ").lower().strip()

            passed: bool | None
            if result == "q":
                self._results.append(
                    StepResult(
                        instruction=step.instruction,
                        expected=step.expected,
                        passed=None,
                        notes="quit early",
                    )
                )
                self._quit_early = True
                break
            elif result == "s":
                passed = None
            else:
                passed = result == "y"

            if result == "y":
                notes = ""
            else:
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

        ts = self._started_at
        filename = f"{self.test_name}_{ts:%Y%m%d_%H%M%S}.json"
        filepath = report_dir / filename

        report_data = {
            "test_name": self.test_name,
            "tester": self.tester,
            "timestamp": ts.isoformat(),
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

    @property
    def quit_early(self) -> bool:
        """Whether the tester pressed 'q' to quit."""
        return self._quit_early

    def failed_steps(self) -> list[StepResult]:
        """Return list of failed steps."""
        return [r for r in self._results if r.passed is False]

    @property
    def results(self) -> list[StepResult]:
        """Get all step results."""
        return self._results.copy()


@pytest.fixture
def interactive_session(request) -> InteractiveSession:
    """Create interactive test session for human verification."""
    return InteractiveSession(test_name=request.node.name)
