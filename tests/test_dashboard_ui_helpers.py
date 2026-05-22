from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.dashboard.ui import format_datetimeish, format_float, format_percent


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, "Unknown"),
        (0, "0%"),
        (1, "100%"),
        (0.125, "12%"),
        ("0.5", "50%"),
        ("not-a-number", "Unknown"),
    ],
)
def test_format_percent(value, expected: str) -> None:
    assert format_percent(value) == expected


def test_format_percent_respects_digits() -> None:
    assert format_percent(0.1234, digits=1) == "12.3%"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, ""),
        (0, "0.000"),
        (1.2, "1.200"),
        ("3.14159", "3.142"),
        ("bad", ""),
    ],
)
def test_format_float(value, expected: str) -> None:
    assert format_float(value) == expected


def test_format_float_respects_digits() -> None:
    assert format_float(3.14159, digits=2) == "3.14"


def test_format_datetimeish_handles_datetime() -> None:
    dt = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    assert format_datetimeish(dt) == "2026-01-02T03:04:05+00:00"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, ""),
        ("", ""),
        ("  ", ""),
        ("2026-01-02", "2026-01-02"),
        ("2026-01-02T03:04:05Z", "2026-01-02T03:04:05Z"),
        ("01/02/2026", "01/02/2026"),
        ("nonsense", ""),
    ],
)
def test_format_datetimeish_handles_strings(value, expected: str) -> None:
    assert format_datetimeish(value) == expected
