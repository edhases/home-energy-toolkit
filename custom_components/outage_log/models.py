"""Data models for the Outage Log integration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.util import dt as dt_util


def _parse_datetime(value: Any) -> datetime | None:
    """Parse a stored ISO timestamp into an aware UTC datetime."""
    if not isinstance(value, str):
        return None

    parsed = dt_util.parse_datetime(value)
    if parsed is None:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt_util.UTC)

    return dt_util.as_utc(parsed)


@dataclass(slots=True)
class Episode:
    """A single grid outage episode."""

    start: datetime
    end: datetime | None = None
    soc_start: float | None = None
    soc_end: float | None = None

    @property
    def duration_seconds(self) -> float | None:
        """Return the duration in seconds, or None while ongoing."""
        if self.end is None:
            return None
        return max(0.0, (self.end - self.start).total_seconds())

    def as_dict(self) -> dict[str, Any]:
        """Serialize the episode for storage."""
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat() if self.end is not None else None,
            "soc_start": self.soc_start,
            "soc_end": self.soc_end,
        }

    @classmethod
    def from_dict(cls, data: Any) -> Episode | None:
        """Deserialize an episode, returning None for malformed data."""
        if not isinstance(data, dict):
            return None

        start = _parse_datetime(data.get("start"))
        if start is None:
            return None

        end = _parse_datetime(data.get("end"))
        if end is not None and end < start:
            end = start

        return cls(
            start=start,
            end=end,
            soc_start=_as_float(data.get("soc_start")),
            soc_end=_as_float(data.get("soc_end")),
        )


def _as_float(value: Any) -> float | None:
    """Return a float value or None."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return round(float(value), 1)
    except (TypeError, ValueError):
        return None
