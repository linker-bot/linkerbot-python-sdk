"""Timer-based motion state tracker with reset support."""

import math
import threading


class MotionTimer:
    """Track motion state using an estimated duration timer.

    Supports resetting the timer when a new motion starts before the
    previous one finishes.

    Usage::

        timer = MotionTimer()
        timer.start(2.0)        # expect motion to take 2s
        timer.is_moving()       # True
        timer.start(3.0)        # new move resets the timer to 3s
        timer.wait_done()       # block until motion finishes
        timer.is_moving()       # False
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._event = threading.Event()
        self._timer: threading.Timer | None = None
        self._generation = 0
        self._event.set()  # not moving initially

    def start(self, duration: float) -> None:
        """Start or reset the motion timer.

        If already moving, cancels the previous timer and starts a new one.
        """
        _validate_timeout(duration, name="duration")
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._generation += 1
            generation = self._generation
            self._event.clear()
            self._timer = threading.Timer(duration, self._on_done, args=(generation,))
            self._timer.daemon = True
            self._timer.start()

    def _on_done(self, generation: int) -> None:
        with self._lock:
            if generation != self._generation:
                return
            self._timer = None
            self._event.set()

    def is_moving(self) -> bool:
        """Return whether motion is in progress."""
        return not self._event.is_set()

    def wait_done(self, timeout: float | None = None) -> bool:
        """Block until motion completes.

        Returns True if motion finished, False if timed out.
        """
        if timeout is not None:
            _validate_timeout(timeout, name="timeout")
        return self._event.wait(timeout)

    def cancel(self) -> None:
        """Cancel the timer and mark motion as done immediately."""
        with self._lock:
            self._generation += 1
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            self._event.set()


def _validate_timeout(value: float, *, name: str) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{name} must be a finite, non-negative number")
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be a finite, non-negative number")
