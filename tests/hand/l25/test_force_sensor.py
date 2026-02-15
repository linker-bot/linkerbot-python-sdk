"""Tests for L25 ForceSensorManager with hardware."""

import pytest

from linkerbot import L25
from tests.conftest import InteractiveSession

pytestmark = [pytest.mark.l25, pytest.mark.sensor]

FINGER_NAMES = ["thumb", "index", "middle", "ring", "pinky"]


class TestForceSensorManagerBlocking:
    """Test ForceSensorManager blocking mode."""

    def test_get_blocking_returns_all_fingers(self, l25_hand: L25):
        """Blocking read should return AllFingersData with all 5 finger attributes."""
        data = l25_hand.force_sensor.get_blocking(timeout_ms=2000)

        assert data is not None
        assert hasattr(data, "thumb")
        assert hasattr(data, "index")
        assert hasattr(data, "middle")
        assert hasattr(data, "ring")
        assert hasattr(data, "pinky")

    def test_each_finger_correct_shape(self, l25_hand: L25):
        """Each finger's force sensor values should have shape (12, 6)."""
        data = l25_hand.force_sensor.get_blocking(timeout_ms=2000)

        for name in FINGER_NAMES:
            finger_data = getattr(data, name)
            assert finger_data.values.shape == (12, 6), (
                f"{name} expected shape (12, 6), got {finger_data.values.shape}"
            )

    def test_each_finger_has_timestamp(self, l25_hand: L25):
        """Each finger's force sensor data should have a positive timestamp."""
        data = l25_hand.force_sensor.get_blocking(timeout_ms=2000)

        for name in FINGER_NAMES:
            finger_data = getattr(data, name)
            assert finger_data.timestamp > 0, (
                f"{name} timestamp should be positive, got {finger_data.timestamp}"
            )

    def test_single_finger_blocking(self, l25_hand: L25):
        """Single finger blocking read should return ForceSensorData with shape (12, 6)."""
        data = l25_hand.force_sensor.get_finger("thumb").get_blocking(timeout_ms=1000)

        assert data is not None
        assert data.values.shape == (12, 6), (
            f"Expected shape (12, 6), got {data.values.shape}"
        )

    def test_all_five_fingers_accessible(self, l25_hand: L25):
        """Each finger should be accessible by name via get_finger()."""
        for name in FINGER_NAMES:
            data = l25_hand.force_sensor.get_finger(name).get_blocking(timeout_ms=1000)
            assert data is not None, f"get_finger({name!r}) returned None"
            assert data.values.shape == (12, 6), (
                f"{name} expected shape (12, 6), got {data.values.shape}"
            )


class TestForceSensorManagerSnapshot:
    """Test ForceSensorManager snapshot mode."""

    def test_snapshot_populated_after_read(self, l25_hand: L25):
        """After get_blocking(), get_snapshot() should return non-None with all 5 fingers."""
        l25_hand.force_sensor.get_blocking(timeout_ms=2000)

        data = l25_hand.force_sensor.get_snapshot()

        assert data is not None, "Snapshot should be populated after blocking read"
        for name in FINGER_NAMES:
            assert hasattr(data, name), f"Snapshot missing finger: {name}"


@pytest.mark.interactive
class TestForceSensorInteractive:
    """Interactive tests for force sensor requiring human verification."""

    def test_thumb_pressure_detection(
        self, l25_hand: L25, interactive_session: InteractiveSession
    ):
        """Human verifies that thumb pressure is detected by force sensor."""
        session = interactive_session

        session.step(
            instruction="Reading thumb force sensor baseline (no pressure applied)",
            action=lambda: print(
                f"\nBaseline thumb values:\n"
                f"{l25_hand.force_sensor.get_finger('thumb').get_blocking(timeout_ms=1000).values}"
            ),
            expected="Baseline values are displayed (no pressure applied yet)",
        ).step(
            instruction="Press firmly on the thumb sensor pad, then press Enter",
            action=lambda: print(
                f"\nThumb values under pressure:\n"
                f"{l25_hand.force_sensor.get_finger('thumb').get_blocking(timeout_ms=1000).values}"
            ),
            expected="Values should have visibly changed compared to baseline",
        )

        session.run()
        session.save_report()

        if session.quit_early:
            pytest.exit("Tester quit early")

        failures = session.failed_steps()
        if failures:
            msgs = [f"- {f.instruction}: {f.notes}" for f in failures]
            pytest.fail(f"{len(failures)} step(s) failed:\n" + "\n".join(msgs))

    def test_each_finger_pressure(
        self, l25_hand: L25, interactive_session: InteractiveSession
    ):
        """Human verifies that each finger's force sensor detects pressure."""
        session = interactive_session

        for name in FINGER_NAMES:
            session.step(
                instruction=f"Press firmly on the {name} finger sensor pad, then press Enter",
                action=lambda n=name: print(
                    f"\n{n} values under pressure:\n"
                    f"{l25_hand.force_sensor.get_finger(n).get_blocking(timeout_ms=1000).values}"
                ),
                expected=f"{name} sensor values should show change from pressure",
            )

        session.run()
        session.save_report()

        if session.quit_early:
            pytest.exit("Tester quit early")

        failures = session.failed_steps()
        if failures:
            msgs = [f"- {f.instruction}: {f.notes}" for f in failures]
            pytest.fail(f"{len(failures)} step(s) failed:\n" + "\n".join(msgs))
