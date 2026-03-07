"""Tests for MotionTimer."""

import time

from linkerbot.motion_timer import MotionTimer


class TestMotionTimer:
    def test_initially_not_moving(self):
        timer = MotionTimer()
        assert not timer.is_moving()

    def test_start_sets_moving(self):
        timer = MotionTimer()
        timer.start(1.0)
        assert timer.is_moving()
        timer.cancel()

    def test_auto_completes_after_duration(self):
        timer = MotionTimer()
        timer.start(0.1)
        assert timer.is_moving()
        time.sleep(0.2)
        assert not timer.is_moving()

    def test_wait_done_blocks_until_complete(self):
        timer = MotionTimer()
        timer.start(0.1)
        result = timer.wait_done(timeout=1.0)
        assert result is True
        assert not timer.is_moving()

    def test_wait_done_returns_false_on_timeout(self):
        timer = MotionTimer()
        timer.start(5.0)
        result = timer.wait_done(timeout=0.05)
        assert result is False
        assert timer.is_moving()
        timer.cancel()

    def test_cancel_stops_immediately(self):
        timer = MotionTimer()
        timer.start(5.0)
        assert timer.is_moving()
        timer.cancel()
        assert not timer.is_moving()

    def test_reset_extends_duration(self):
        timer = MotionTimer()
        timer.start(0.1)
        time.sleep(0.05)
        # reset with a longer duration before the first one expires
        timer.start(0.2)
        time.sleep(0.1)
        # original 0.1s would have expired, but reset extended it
        assert timer.is_moving()
        timer.wait_done(timeout=1.0)
        assert not timer.is_moving()

    def test_reset_during_motion(self):
        timer = MotionTimer()
        timer.start(0.1)
        assert timer.is_moving()
        timer.start(0.1)
        assert timer.is_moving()
        timer.wait_done(timeout=1.0)
        assert not timer.is_moving()

    def test_start_after_completed(self):
        timer = MotionTimer()
        timer.start(0.05)
        time.sleep(0.1)
        assert not timer.is_moving()
        # start again
        timer.start(0.05)
        assert timer.is_moving()
        timer.wait_done(timeout=1.0)
        assert not timer.is_moving()

    def test_cancel_when_not_moving_is_noop(self):
        timer = MotionTimer()
        timer.cancel()  # should not raise
        assert not timer.is_moving()

    def test_wait_done_when_not_moving_returns_immediately(self):
        timer = MotionTimer()
        start = time.monotonic()
        result = timer.wait_done(timeout=5.0)
        elapsed = time.monotonic() - start
        assert result is True
        assert elapsed < 0.1
