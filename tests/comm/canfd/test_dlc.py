import pytest

from linkerbot.comm.canfd import dlc_to_length, length_to_dlc
from linkerbot.exceptions import ValidationError


@pytest.mark.parametrize(
    ("length", "dlc"),
    [
        (0, 0),
        (1, 1),
        (8, 8),
        (9, 9),
        (12, 9),
        (13, 10),
        (16, 10),
        (17, 11),
        (20, 11),
        (21, 12),
        (24, 12),
        (25, 13),
        (32, 13),
        (33, 14),
        (48, 14),
        (49, 15),
        (64, 15),
    ],
)
def test_length_to_dlc_boundaries(length: int, dlc: int) -> None:
    assert length_to_dlc(length) == dlc


@pytest.mark.parametrize(
    ("dlc", "length"),
    [
        (0, 0),
        (1, 1),
        (8, 8),
        (9, 12),
        (10, 16),
        (11, 20),
        (12, 24),
        (13, 32),
        (14, 48),
        (15, 64),
    ],
)
def test_dlc_to_length(dlc: int, length: int) -> None:
    assert dlc_to_length(dlc) == length


@pytest.mark.parametrize("length", [-1, 65])
def test_length_to_dlc_rejects_invalid_length(length: int) -> None:
    with pytest.raises(ValidationError):
        length_to_dlc(length)


@pytest.mark.parametrize("dlc", [-1, 16])
def test_dlc_to_length_rejects_invalid_dlc(dlc: int) -> None:
    with pytest.raises(ValidationError):
        dlc_to_length(dlc)
