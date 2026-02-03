"""Iterable queue implementation with Go channel-like semantics.

This module provides the IterableQueue class that supports iteration,
similar to Go channels. The queue blocks when empty during iteration
and only stops when explicitly closed or when an exception occurs.
"""

import queue
from typing import TypeVar

from linkerbot.exceptions import StateError

T = TypeVar("T")

_POLL_TIMEOUT = 0.1


class IterableQueue[T]:
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

    def __init__(self, maxsize: int = 0):
        """Initialize the iterable queue.

        Args:
            maxsize: Maximum queue size (0 = unlimited).
        """
        self._queue: queue.Queue[T] = queue.Queue(maxsize=maxsize)
        self._closed = False

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
        if self._closed:
            raise StateError("Cannot put to a closed queue")
        self._queue.put(item, block=block, timeout=timeout)

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
        if self._closed and self._queue.empty():
            raise StopIteration

        if not block:
            return self._queue.get(block=False, timeout=timeout)

        # Blocking mode: poll with timeout to check closed state
        while True:
            try:
                return self._queue.get(block=True, timeout=_POLL_TIMEOUT)
            except queue.Empty:
                continue

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
        return self._queue.empty()

    def close(self) -> None:
        """Close the queue and signal end of iteration.

        After closing, any blocking get() or iteration will stop once the queue is empty.
        New items cannot be added after closing.
        """
        self._closed = True

    def __iter__(self):
        """Return iterator for the queue."""
        return self

    def __next__(self):
        """Get next item from queue, blocking until available.

        This enables for-loop iteration over the queue. It blocks when the queue
        is empty, similar to reading from a Go channel.

        Returns:
            Next item from the queue.

        Raises:
            StopIteration: When queue is closed and empty.
        """
        return self.get(block=True)
