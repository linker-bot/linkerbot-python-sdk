"""Compatibility helpers for observing queued CAN FD send results."""

from __future__ import annotations

import builtins
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import Protocol

from linkerbot.exceptions import TimeoutError as SDKTimeoutError

_SEND_RECEIPT_TIMEOUT_S = 1.0


class SendReceiptLike(Protocol):
    """Minimal Future-like result contract returned by new dispatchers."""

    def result(self, timeout: float | None = None) -> object:
        """Wait for the physical send result."""
        ...


def wait_for_send_receipt(receipt: SendReceiptLike | None) -> None:
    """Wait boundedly when a dispatcher exposes a physical-send receipt."""
    if receipt is None:
        return
    try:
        receipt.result(timeout=_SEND_RECEIPT_TIMEOUT_S)
    except SDKTimeoutError:
        raise
    except (builtins.TimeoutError, FutureTimeoutError) as error:
        raise SDKTimeoutError(
            "CAN FD physical send did not complete within "
            f"{_SEND_RECEIPT_TIMEOUT_S * 1000:.0f}ms; send outcome is unknown"
        ) from error


__all__ = ["SendReceiptLike", "wait_for_send_receipt"]
