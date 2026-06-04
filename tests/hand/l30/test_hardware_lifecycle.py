from __future__ import annotations

import pytest

from tests.hand.l30.hardware_helpers import open_l30, require_full_hardware

pytestmark = [
    pytest.mark.l30,
    pytest.mark.canfd,
    pytest.mark.hardware,
    pytest.mark.interactive,
]


def test_l30_hardware_lifecycle_open_close() -> None:
    require_full_hardware()

    with open_l30() as hand:
        assert not hand.is_closed()

    assert hand.is_closed()


def test_l30_hardware_explicit_close_is_idempotent() -> None:
    require_full_hardware()

    with open_l30() as hand:
        hand.close()
        hand.close()

    assert hand.is_closed()
