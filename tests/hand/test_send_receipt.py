"""Tests for optional CAN FD physical-send receipts."""

from __future__ import annotations

import builtins
from concurrent.futures import Future
from concurrent.futures import TimeoutError as FutureTimeoutError

import pytest

from linkerbot.exceptions import TimeoutError
from linkerbot.hand import _send_receipt


def test_none_receipt_keeps_legacy_dispatchers_compatible() -> None:
    _send_receipt.wait_for_send_receipt(None)


def test_receipt_timeout_marks_send_outcome_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_send_receipt, "_SEND_RECEIPT_TIMEOUT_S", 0.001)
    receipt = Future[None]()

    with pytest.raises(TimeoutError, match="send outcome is unknown") as raised:
        _send_receipt.wait_for_send_receipt(receipt)

    assert isinstance(
        raised.value.__cause__, (builtins.TimeoutError, FutureTimeoutError)
    )


def test_sdk_timeout_from_backend_is_preserved() -> None:
    expected = TimeoutError("backend timed out")
    receipt = Future[None]()
    receipt.set_exception(expected)

    with pytest.raises(TimeoutError) as raised:
        _send_receipt.wait_for_send_receipt(receipt)

    assert raised.value is expected
