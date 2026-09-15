"""Iterable queue implementation with Go channel-like semantics.

This module provides the IterableQueue class that supports iteration,
similar to Go channels. The queue blocks when empty during iteration
and only stops when explicitly closed or when an exception occurs.
"""

import math
import queue
import threading
import time
from collections import deque
from collections.abc import Iterator
from typing import Generic, TypeVar

from linkerbot.exceptions import StateError

T = TypeVar("T")


class IterableQueue(Generic[T]):
    """Queue wrapper that supports iteration like Go channels.

    This queue blocks when empty during iteration, similar to Go channel behavior.
    Iteration only stops when explicitly closed or when an exception occurs.

    Type Parameters:
        T: The type of items stored in the queue.

    Example:
        >>> q = IterableQueue[ForceSensorData]()
        >>> # Producer thread
        >>> q.put(data1)
        >>> q.put(data2)
        >>> q.close()  # Signal end of data
        >>>
        >>> # Consumer with for loop
        >>> for data in q:
        ...     process(data)  # Blocks waiting for data when queue is empty
    """

    def __init__(self, maxsize: int = 0) -> None:
        """Initialize the iterable queue.

        Args:
            maxsize: Maximum queue size (0 = unlimited).
        """
        self._items: deque[T] = deque()
        self._maxsize = maxsize
        self._closed = False
        self._condition = threading.Condition()

    def put(self, item: T, block: bool = True, timeout: float | None = None) -> None:
        """Put an item into the queue.

        Args:
            item: Item to put in the queue.
            block: Whether to block if queue is full.
            timeout: Optional timeout in seconds.

        Raises:
            queue.Full: If queue is full and block=False or timeout expires.
            StateError: If queue is already closed.
        """
        _validate_timeout(block=block, timeout=timeout)
        deadline = None if timeout is None else time.monotonic() + timeout

        with self._condition:
            if self._closed:
                raise StateError("Cannot put to a closed queue")

            while self._is_full():
                if not block:
                    raise queue.Full
                remaining = _remaining_time(deadline)
                if remaining == 0:
                    raise queue.Full
                self._condition.wait(remaining)
                if self._closed:
                    raise StateError("Cannot put to a closed queue")

            self._items.append(item)
            self._condition.notify_all()

    def put_nowait(self, item: T) -> None:
        """Put an item without blocking.

        Args:
            item: Item to put in the queue.

        Raises:
            queue.Full: If queue is full.
            StateError: If queue is already closed.
        """
        self.put(item, block=False)

    def get(self, block: bool = True, timeout: float | None = None) -> T:
        """Get an item from the queue.

        Args:
            block: Whether to block if queue is empty.
            timeout: Optional timeout in seconds.

        Returns:
            Item from the queue.

        Raises:
            queue.Empty: If queue is empty and block=False or timeout expires.
            StopIteration: If queue is closed and empty.
        """
        _validate_timeout(block=block, timeout=timeout)

        deadline = None if timeout is None else time.monotonic() + timeout
        with self._condition:
            while not self._items:
                if self._closed:
                    raise StopIteration
                if not block:
                    raise queue.Empty
                remaining = _remaining_time(deadline)
                if remaining == 0:
                    raise queue.Empty
                self._condition.wait(remaining)

            item = self._items.popleft()
            self._condition.notify_all()
            return item

    def get_nowait(self) -> T:
        """Get an item without blocking.

        Returns:
            Item from the queue.

        Raises:
            queue.Empty: If queue is empty.
            StopIteration: If queue is closed and empty.
        """
        return self.get(block=False)

    def empty(self) -> bool:
        """Check if queue is empty.

        Returns:
            True if queue is empty, False otherwise.
        """
        with self._condition:
            return not self._items

    def close(self) -> None:
        """Close the queue and signal end of iteration.

        After closing, any blocking get() or iteration will stop once the queue is empty.
        New items cannot be added after closing.
        """
        with self._condition:
            self._closed = True
            self._condition.notify_all()

    def __iter__(self) -> Iterator[T]:
        """Return iterator for the queue."""
        return self

    def __next__(self) -> T:
        """Get next item from queue, blocking until available.

        This enables for-loop iteration over the queue. It blocks when the queue
        is empty, similar to reading from a Go channel.

        Returns:
            Next item from the queue.

        Raises:
            StopIteration: When queue is closed and empty.
        """
        return self.get(block=True)

    def _is_full(self) -> bool:
        return self._maxsize > 0 and len(self._items) >= self._maxsize


def _validate_timeout(*, block: bool, timeout: float | None) -> None:
    if not block and timeout is not None:
        raise ValueError("timeout must not be specified when block is False")
    if timeout is None:
        return
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool):
        raise ValueError("timeout must be a finite, non-negative number")
    if not math.isfinite(timeout) or timeout < 0:
        raise ValueError("timeout must be a finite, non-negative number")


def _remaining_time(deadline: float | None) -> float | None:
    if deadline is None:
        return None
    return max(0.0, deadline - time.monotonic())
