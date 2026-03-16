"""Tests for L6 ForceSensorManager with hardware."""

import time

import pytest

from linkerbot import L6
from linkerbot.hand.l6 import SensorSource
from tests.conftest import InteractiveSession

pytestmark = [pytest.mark.l6, pytest.mark.sensor]

FINGER_NAMES = ["thumb", "index", "middle", "ring", "pinky"]
PRESSURE_THRESHOLD = 20  # mean value above this → pressed; tune to hardware


class TestForceSensorBlocking:
    """Test ForceSensorManager blocking reads against real hardware."""

    def test_blocking_double_read_and_baseline(self, l6_hand: L6):
        """Open pose, two reads 0.2s apart, verify shape and timestamps."""
        l6_hand.angle.set_angles([100.0] * 6)
        time.sleep(2.0)

        # First read
        data1 = l6_hand.force_sensor.get_blocking(timeout_ms=2000)
        assert data1 is not None

        for name in FINGER_NAMES:
            finger = getattr(data1, name)
            assert finger.values.shape == (12, 6), (
                f"{name} expected shape (12, 6), got {finger.values.shape}"
            )
            assert finger.timestamp > 0

        print("\n  --- No-load baseline (open pose) ---")
        for name in FINGER_NAMES:
            finger = getattr(data1, name)
            print(
                f"  {name}: mean={finger.values.mean():.2f}  values=\n{finger.values}"
            )

        time.sleep(0.2)

        # Second read
        data2 = l6_hand.force_sensor.get_blocking(timeout_ms=2000)
        assert data2 is not None

        # Timestamp must increase per finger
        for name in FINGER_NAMES:
            t1 = getattr(data1, name).timestamp
            t2 = getattr(data2, name).timestamp
            assert t2 > t1, (
                f"{name} second timestamp ({t2:.4f}) should be > first ({t1:.4f})"
            )

        print("\n  Second read timestamps are later — OK")

    def test_each_finger_accessible(self, l6_hand: L6):
        """Each finger should be accessible by name via get_finger()."""
        for name in FINGER_NAMES:
            data = l6_hand.force_sensor.get_finger(name).get_blocking(timeout_ms=1000)
            assert data is not None, f"get_finger({name!r}) returned None"
            assert data.values.shape == (12, 6), (
                f"{name} expected shape (12, 6), got {data.values.shape}"
            )

    def test_snapshot_populated_after_read(self, l6_hand: L6):
        """After get_blocking(), get_snapshot() returns non-None with all 5 fingers."""
        l6_hand.force_sensor.get_blocking(timeout_ms=2000)

        data = l6_hand.force_sensor.get_snapshot()
        assert data is not None, "Snapshot should be populated after blocking read"
        for name in FINGER_NAMES:
            assert hasattr(data, name), f"Snapshot missing finger: {name}"


@pytest.mark.interactive
class TestForceSensorInteractive:
    """Interactive per-finger pressure test (thumb → pinky)."""

    def test_per_finger_pressure(
        self, l6_hand: L6, interactive_session: InteractiveSession
    ):
        """Per-finger pressure: thumb→pinky, one session.run(), user confirms all."""
        session = interactive_session

        for name in FINGER_NAMES:

            def _read_and_print(n: str = name) -> None:
                data = l6_hand.force_sensor.get_finger(n).get_blocking(timeout_ms=2000)
                print(f"\n  [{n}] mean={data.values.mean():.2f}")
                print(f"  {data.values}")

            session.step(
                instruction=f"Press firmly on the {name} sensor pad, then press Enter",
                action=_read_and_print,
                expected=(
                    f"{name} sensor values should show higher readings compared to baseline"
                ),
            )

        session.run()
        session.save_report()

        if session.quit_early:
            pytest.exit("Tester quit early")

        failures = session.failed_steps()
        if failures:
            msgs = [f"- {f.instruction}: {f.notes}" for f in failures]
            pytest.fail(f"{len(failures)} step(s) failed:\n" + "\n".join(msgs))


@pytest.mark.interactive
class TestForceSensorStreaming:
    """Streaming auto-detect: poll at 50ms, detect each finger by threshold."""

    def test_streaming_all_fingers_detected(self, l6_hand: L6):
        """Prompt user to release fingers, poll 50ms, auto-detect all 5, pass/fail."""
        print("\n  [Streaming pressure detection]")
        print("  Please RELEASE all fingers — do NOT press any sensor.")
        input("  Press Enter when ready...")

        detected: set[str] = set()
        TIMEOUT_S = 60.0
        deadline = time.monotonic() + TIMEOUT_S

        try:
            l6_hand.start_polling({SensorSource.FORCE_SENSOR: 0.05})

            print(
                "\n  Now press each finger sensor one by one "
                "(thumb → index → middle → ring → pinky)."
            )
            print("  Detection is automatic — no Enter needed.\n")

            while time.monotonic() < deadline:
                time.sleep(0.05)
                snapshot = l6_hand.force_sensor.get_snapshot()
                if snapshot is None:
                    continue

                for name in FINGER_NAMES:
                    if name in detected:
                        continue
                    finger_data = getattr(snapshot, name)
                    mean_val = float(finger_data.values.mean())
                    if mean_val > PRESSURE_THRESHOLD:
                        detected.add(name)
                        print(f"  ✓ {name} detected! mean={mean_val:.2f}")

                if len(detected) == len(FINGER_NAMES):
                    print("\n  All 5 fingers detected — test passed!")
                    break
            else:
                missing = sorted(set(FINGER_NAMES) - detected)
                pytest.fail(
                    f"Timeout after {TIMEOUT_S}s. Fingers not detected: {missing}"
                )
        finally:
            l6_hand.stop_polling()
