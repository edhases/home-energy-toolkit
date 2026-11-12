"""Tariff and billing-period helpers for the Energy Cost integration."""

from __future__ import annotations

from datetime import date, timedelta
from datetime import time as dt_time
from typing import Any

from .const import (
    TARIFF_DAY,
    TARIFF_MODE_DUAL,
    TARIFF_MODE_SINGLE,
    TARIFF_NIGHT,
)


def parse_clock(value: Any, fallback: dt_time) -> dt_time:
    """Parse a HH:MM string (or time object) into a naive time."""
    if isinstance(value, dt_time):
        return value.replace(tzinfo=None)
    if isinstance(value, str):
        try:
            return dt_time.fromisoformat(value).replace(tzinfo=None)
        except ValueError:
            return fallback
    return fallback


def format_clock(value: Any, fallback: str) -> str:
    """Normalize a stored time value to HH:MM."""
    default = parse_clock(fallback, dt_time(0, 0))
    parsed = parse_clock(value, default)
    return parsed.strftime("%H:%M")


def billing_period_start(today: date, start_day: int) -> date:
    """Return the start date of the billing period containing today."""
    start_day = max(1, min(28, start_day))
    if today.day >= start_day:
        return date(today.year, today.month, start_day)
    previous_month_end = date(today.year, today.month, 1) - timedelta(days=1)
    return date(previous_month_end.year, previous_month_end.month, start_day)


def month_key(today: date) -> str:
    """Return a stable key for the calendar month."""
    return f"{today.year:04d}-{today.month:02d}"


def is_night(now: dt_time, night_start: dt_time, night_end: dt_time) -> bool:
    """Return True when the current time is inside the night window."""
    if night_start == night_end:
        return False
    if night_start < night_end:
        return night_start <= now < night_end
    return now >= night_start or now < night_end


def active_tariff(
    tariff_mode: str,
    night_start: dt_time,
    night_end: dt_time,
    now: dt_time,
) -> str:
    """Return the tariff state that applies right now."""
    if tariff_mode != TARIFF_MODE_DUAL:
        return TARIFF_MODE_SINGLE
    return TARIFF_NIGHT if is_night(now, night_start, night_end) else TARIFF_DAY
