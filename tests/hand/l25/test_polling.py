"""Tests for L25 polling with real hardware."""

import time

import pytest

from linkerbot import L25
from linkerbot.hand.l25 import SensorSource

pytestmark = [pytest.mark.l25, pytest.mark.polling]


class TestPolling:
    """Test L25 polling functionality against real hardware."""

    def test_start_polling_single_source(self, l25_hand: L25):
        """Polling a single source should populate its snapshot."""
        try:
            l25_hand.start_polling({SensorSource.ANGLE: 0.1})
            time.sleep(0.5)

            data = l25_hand.angle.get_snapshot()
            assert data is not None, "Angle snapshot should not be None after polling"
        finally:
            l25_hand.stop_polling()

    def test_start_polling_multiple_sources(self, l25_hand: L25):
        """Polling multiple sources should populate all their snapshots."""
        try:
            l25_hand.start_polling(
                {
                    SensorSource.ANGLE: 0.1,
                    SensorSource.TORQUE: 0.1,
                    SensorSource.TEMPERATURE: 0.1,
                }
            )
            time.sleep(1)

            angle = l25_hand.angle.get_snapshot()
            torque = l25_hand.torque.get_snapshot()
            temperature = l25_hand.temperature.get_snapshot()

            assert angle is not None, "Angle snapshot should not be None"
            assert torque is not None, "Torque snapshot should not be None"
            assert temperature is not None, "Temperature snapshot should not be None"
        finally:
            l25_hand.stop_polling()

    def test_snapshot_updates_over_time(self, l25_hand: L25):
        """Snapshot timestamp should advance as polling continues."""
        try:
            l25_hand.start_polling({SensorSource.ANGLE: 0.1})
            time.sleep(0.3)

            snap1 = l25_hand.get_snapshot()
            timestamp1 = snap1.timestamp

            time.sleep(0.3)

            snap2 = l25_hand.get_snapshot()
            timestamp2 = snap2.timestamp

            assert timestamp2 > timestamp1, (
                f"Second timestamp ({timestamp2}) should be greater than first ({timestamp1})"
            )
        finally:
            l25_hand.stop_polling()

    def test_snapshot_frozen_after_stop(self, l25_hand: L25):
        """After stop_polling, snapshot should exist but not advance rapidly."""
        try:
            l25_hand.start_polling({SensorSource.ANGLE: 0.1})
            time.sleep(0.5)
        finally:
            l25_hand.stop_polling()

        snap = l25_hand.angle.get_snapshot()
        assert snap is not None, "Snapshot should exist after polling stopped"
        ts1 = snap.timestamp

        time.sleep(0.3)

        snap2 = l25_hand.angle.get_snapshot()
        assert snap2 is not None
        assert snap2.timestamp == ts1, "Snapshot should not update after stop_polling"

    def test_stop_polling_clean(self, l25_hand: L25):
        """stop_polling should be idempotent and not raise errors."""
        try:
            l25_hand.start_polling({SensorSource.ANGLE: 0.1})
            l25_hand.stop_polling()
            l25_hand.stop_polling()  # Second call should not raise
        finally:
            l25_hand.stop_polling()

    def test_polling_all_sources(self, l25_hand: L25):
        """Polling with all sources explicitly specified should populate all snapshots."""
        try:
            l25_hand.start_polling(
                {
                    SensorSource.ANGLE: 0.1,
                    SensorSource.SPEED: 0.1,
                    SensorSource.TORQUE: 0.1,
                    SensorSource.TEMPERATURE: 0.1,
                    SensorSource.FAULT: 0.1,
                    SensorSource.FORCE_SENSOR: 0.1,
                }
            )
            time.sleep(1.5)

            snapshot = l25_hand.get_snapshot()

            assert snapshot.angle is not None, "Angle should not be None"
            assert snapshot.torque is not None, "Torque should not be None"
            assert snapshot.temperature is not None, "Temperature should not be None"
            assert snapshot.force_sensor is not None, "Force sensor should not be None"
            assert snapshot.fault is not None, "Fault should not be None"
        finally:
            l25_hand.stop_polling()

    def test_get_snapshot_reflects_polling_data(self, l25_hand: L25):
        """get_snapshot should reflect data from polled sources."""
        try:
            l25_hand.start_polling(
                {
                    SensorSource.ANGLE: 0.1,
                    SensorSource.TEMPERATURE: 0.1,
                }
            )
            time.sleep(1)

            snapshot = l25_hand.get_snapshot()

            assert snapshot.angle is not None, "Angle should not be None"
            assert snapshot.temperature is not None, "Temperature should not be None"
        finally:
            l25_hand.stop_polling()
