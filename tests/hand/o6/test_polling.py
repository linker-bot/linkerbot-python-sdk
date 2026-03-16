"""Tests for O6 polling with real hardware."""

import time

import pytest

from linkerbot import O6
from linkerbot.hand.o6 import SensorSource

pytestmark = [pytest.mark.o6, pytest.mark.polling]


class TestPolling:
    """Test O6 polling functionality against real hardware."""

    def test_start_polling_single_source(self, o6_hand: O6):
        """Polling a single source should populate its snapshot."""
        try:
            o6_hand.start_polling({SensorSource.ANGLE: 0.1})
            time.sleep(0.5)

            data = o6_hand.angle.get_snapshot()
            assert data is not None, "Angle snapshot should not be None after polling"
        finally:
            o6_hand.stop_polling()

    def test_start_polling_multiple_sources(self, o6_hand: O6):
        """Polling multiple sources should populate all their snapshots."""
        try:
            o6_hand.start_polling(
                {
                    SensorSource.ANGLE: 0.1,
                    SensorSource.TORQUE: 0.1,
                    SensorSource.TEMPERATURE: 0.1,
                }
            )
            time.sleep(1)

            angle = o6_hand.angle.get_snapshot()
            torque = o6_hand.torque.get_snapshot()
            temperature = o6_hand.temperature.get_snapshot()

            assert angle is not None, "Angle snapshot should not be None"
            assert torque is not None, "Torque snapshot should not be None"
            assert temperature is not None, "Temperature snapshot should not be None"
        finally:
            o6_hand.stop_polling()

    def test_snapshot_updates_over_time(self, o6_hand: O6):
        """Snapshot timestamp should advance as polling continues."""
        try:
            o6_hand.start_polling({SensorSource.ANGLE: 0.1})
            time.sleep(0.3)

            snap1 = o6_hand.get_snapshot()
            timestamp1 = snap1.timestamp

            time.sleep(0.3)

            snap2 = o6_hand.get_snapshot()
            timestamp2 = snap2.timestamp

            assert timestamp2 > timestamp1, (
                f"Second timestamp ({timestamp2}) should be greater than first ({timestamp1})"
            )
        finally:
            o6_hand.stop_polling()

    def test_snapshot_frozen_after_stop(self, o6_hand: O6):
        """After stop_polling, snapshot should exist but not advance rapidly."""
        try:
            o6_hand.start_polling({SensorSource.ANGLE: 0.1})
            time.sleep(0.5)
        finally:
            o6_hand.stop_polling()

        snap = o6_hand.angle.get_snapshot()
        assert snap is not None, "Snapshot should exist after polling stopped"
        ts1 = snap.timestamp

        time.sleep(0.3)

        snap2 = o6_hand.angle.get_snapshot()
        assert snap2 is not None
        assert snap2.timestamp == ts1, "Snapshot should not update after stop_polling"

    def test_stop_polling_clean(self, o6_hand: O6):
        """stop_polling should be idempotent and not raise errors."""
        try:
            o6_hand.start_polling({SensorSource.ANGLE: 0.1})
            o6_hand.stop_polling()
            o6_hand.stop_polling()  # Second call should not raise
        finally:
            o6_hand.stop_polling()

    def test_polling_all_sources(self, o6_hand: O6):
        """Polling with all sources explicitly specified should populate all snapshots."""
        try:
            o6_hand.start_polling(
                {
                    SensorSource.ANGLE: 0.1,
                    SensorSource.TORQUE: 0.1,
                    SensorSource.SPEED: 0.1,
                    SensorSource.ACCELERATION: 0.1,
                    SensorSource.TEMPERATURE: 0.1,
                    SensorSource.FAULT: 0.1,
                }
            )
            time.sleep(1.5)

            snapshot = o6_hand.get_snapshot()

            assert snapshot.angle is not None, "Angle should not be None"
            assert snapshot.torque is not None, "Torque should not be None"
            assert snapshot.temperature is not None, "Temperature should not be None"
            assert snapshot.speed is not None, "Speed should not be None"
            assert snapshot.acceleration is not None, "Acceleration should not be None"
            assert snapshot.fault is not None, "Fault should not be None"
        finally:
            o6_hand.stop_polling()

    def test_get_snapshot_reflects_polling_data(self, o6_hand: O6):
        """get_snapshot should reflect data from polled sources."""
        try:
            o6_hand.start_polling(
                {
                    SensorSource.ANGLE: 0.1,
                    SensorSource.TEMPERATURE: 0.1,
                }
            )
            time.sleep(1)

            snapshot = o6_hand.get_snapshot()

            assert snapshot.angle is not None, "Angle should not be None"
            assert snapshot.temperature is not None, "Temperature should not be None"
        finally:
            o6_hand.stop_polling()
