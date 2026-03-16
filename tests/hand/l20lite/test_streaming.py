"""Tests for L20Lite streaming with real hardware."""

import threading
import time

import pytest

from linkerbot import L20lite
from linkerbot.hand.l20lite import (
    AngleEvent,
    SensorSource,
    TemperatureEvent,
    TorqueEvent,
)

pytestmark = [pytest.mark.l20lite, pytest.mark.streaming]


class TestStreaming:
    """Test L20lite streaming functionality against real hardware."""

    def test_stream_receives_events(self, l20lite_hand: L20lite):
        """Stream should receive at least one event."""
        events = []
        try:
            l20lite_hand.start_polling({SensorSource.ANGLE: 0.1})
            queue = l20lite_hand.stream()

            def collect():
                for event in queue:
                    events.append(event)

            t = threading.Thread(target=collect, daemon=True)
            t.start()
            time.sleep(2)
            l20lite_hand.stop_stream()
            t.join(timeout=2)

            assert len(events) >= 1, "Should have received at least 1 event"
        finally:
            l20lite_hand.stop_stream()
            l20lite_hand.stop_polling()

    def test_stream_event_types_match_sources(self, l20lite_hand: L20lite):
        """When polling only ANGLE, all events should be AngleEvent."""
        events = []
        try:
            l20lite_hand.start_polling({SensorSource.ANGLE: 0.1})
            queue = l20lite_hand.stream()

            def collect():
                for event in queue:
                    events.append(event)

            t = threading.Thread(target=collect, daemon=True)
            t.start()
            time.sleep(2)
            l20lite_hand.stop_stream()
            t.join(timeout=2)

            assert len(events) >= 1, "Should have received at least 1 event"
            for event in events:
                assert isinstance(event, AngleEvent), (
                    f"Expected AngleEvent, got {type(event).__name__}"
                )
        finally:
            l20lite_hand.stop_stream()
            l20lite_hand.stop_polling()

    def test_stream_multiple_event_types(self, l20lite_hand: L20lite):
        """When polling ANGLE and TORQUE, both event types should appear."""
        events: list = []
        try:
            l20lite_hand.start_polling(
                {SensorSource.ANGLE: 0.1, SensorSource.TORQUE: 0.1}
            )
            queue = l20lite_hand.stream()

            def collect() -> None:
                for event in queue:
                    events.append(event)

            t = threading.Thread(target=collect, daemon=True)
            t.start()
            time.sleep(2)

            l20lite_hand.stop_stream()
            t.join(timeout=2)

            assert len(events) >= 1, "Should have received at least 1 event"
            has_angle = any(isinstance(e, AngleEvent) for e in events)
            has_torque = any(isinstance(e, TorqueEvent) for e in events)
            assert has_angle, "Should have received at least one AngleEvent"
            assert has_torque, "Should have received at least one TorqueEvent"
        finally:
            l20lite_hand.stop_stream()
            l20lite_hand.stop_polling()

    def test_stream_event_has_valid_data(self, l20lite_hand: L20lite):
        """AngleEvent data should contain 10 angles in [0, 100]."""
        events = []
        try:
            l20lite_hand.start_polling({SensorSource.ANGLE: 0.1})
            queue = l20lite_hand.stream()

            def collect():
                for event in queue:
                    events.append(event)

            t = threading.Thread(target=collect, daemon=True)
            t.start()
            time.sleep(2)
            l20lite_hand.stop_stream()
            t.join(timeout=2)

            angle_events = [e for e in events if isinstance(e, AngleEvent)]
            assert len(angle_events) >= 1, (
                "Should have received at least one AngleEvent"
            )

            first = angle_events[0]
            angles = first.data.angles.to_list()
            assert len(angles) == 10, f"Expected 10 angles, got {len(angles)}"
            for angle in angles:
                assert 0 <= angle <= 100, f"Angle {angle} out of range [0, 100]"
        finally:
            l20lite_hand.stop_stream()
            l20lite_hand.stop_polling()

    def test_stream_stop_idempotent_and_reopen(self, l20lite_hand: L20lite):
        """stop_stream is idempotent; re-opening stream should not raise."""
        try:
            l20lite_hand.start_polling(
                {SensorSource.ANGLE: 0.1, SensorSource.TEMPERATURE: 0.1}
            )
            queue = l20lite_hand.stream()
            assert queue is not None

            l20lite_hand.stop_stream()
            l20lite_hand.stop_stream()  # idempotent

            # Re-open
            queue2 = l20lite_hand.stream()
            assert queue2 is not None

            angle_events: list[AngleEvent] = []
            temp_events: list[TemperatureEvent] = []

            def collect() -> None:
                for event in queue2:
                    if isinstance(event, AngleEvent):
                        angle_events.append(event)
                    elif isinstance(event, TemperatureEvent):
                        temp_events.append(event)

            t = threading.Thread(target=collect, daemon=True)
            t.start()
            time.sleep(0.5)
            l20lite_hand.stop_stream()
            t.join(timeout=2)

            # Verify re-opened stream delivered valid angle data
            assert len(angle_events) >= 1, "Re-opened stream should deliver events"
            first = angle_events[0]
            angles = first.data.angles.to_list()
            assert len(angles) == 10
            for angle in angles:
                assert 0 <= angle <= 100, f"Angle {angle} out of range [0, 100]"
        finally:
            l20lite_hand.stop_stream()
            l20lite_hand.stop_polling()

    def test_stop_stream_clean(self, l20lite_hand: L20lite):
        """stop_stream should not raise errors."""
        try:
            l20lite_hand.start_polling({SensorSource.ANGLE: 0.1})
            l20lite_hand.stream()
            l20lite_hand.stop_stream()
        finally:
            l20lite_hand.stop_stream()
            l20lite_hand.stop_polling()

    def test_stream_pattern_matching(self, l20lite_hand: L20lite):
        """Events should be categorizable via match/case."""
        events: list = []
        try:
            l20lite_hand.start_polling(
                {
                    SensorSource.ANGLE: 0.1,
                    SensorSource.TEMPERATURE: 0.1,
                }
            )
            queue = l20lite_hand.stream()

            def collect() -> None:
                for event in queue:
                    events.append(event)

            t = threading.Thread(target=collect, daemon=True)
            t.start()
            time.sleep(0.5)
            l20lite_hand.stop_stream()
            t.join(timeout=2)

            angle_count = 0
            temperature_count = 0
            for event in events:
                match event:
                    case AngleEvent():
                        angle_count += 1
                    case TemperatureEvent():
                        temperature_count += 1

            assert angle_count >= 1, "Should have matched at least one AngleEvent"
            assert temperature_count >= 1, (
                "Should have matched at least one TemperatureEvent"
            )
        finally:
            l20lite_hand.stop_stream()
            l20lite_hand.stop_polling()
