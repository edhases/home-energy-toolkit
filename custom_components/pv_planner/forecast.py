"""Forecast.Solar client and data coordinator.

Forecast.Solar is polled at most once per hour: the free tier allows twelve
requests per hour and the coordinator interval is clamped to at least 60
minutes. Responses are parsed into an easily queryable, immutable object so
the sensor platform can interpolate and integrate the curve without doing any
network work itself.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Final

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .calculations import as_float
from .const import (
    CONF_AZIMUTH,
    CONF_DECLINATION,
    CONF_FORECAST_POLL_MINUTES,
    CONF_KWP,
    DEFAULT_FORECAST_POLL_MINUTES,
    DEFAULT_KWP,
    FORECAST_SOLAR_TIMEOUT,
    FORECAST_SOLAR_URL,
    MIN_FORECAST_POLL_MINUTES,
    NAME,
    PROVIDER_FORECAST_SOLAR,
)

_LOGGER = logging.getLogger(__name__)

_WATTS: Final = "watts"
_WATT_HOURS_DAY: Final = "watt_hours_day"


@dataclass(frozen=True, slots=True)
class ForecastSolarData:
    """Parsed Forecast.Solar estimate.

    ``watts`` is a sorted tuple of ``(local datetime, W)`` points.
    ``watt_hours_day`` maps an ISO date to Wh, exactly as the API returns it.
    """

    watts: tuple[tuple[datetime, float], ...]
    watt_hours_day: Mapping[str, float]
    fetched_at: datetime
    provider: str = PROVIDER_FORECAST_SOLAR

    def value_at(self, when: datetime) -> float | None:
        """Return the interpolated forecast power in W at *when*."""
        if not self.watts:
            return None

        first_time = self.watts[0][0]
        last_time, last_watts = self.watts[-1]

        # The forecast starts and ends at zero, so anything outside the curve
        # is night time.
        if when < first_time:
            return 0.0
        if when > last_time:
            return 0.0
        if when == last_time:
            return last_watts

        for (start_time, start_watts), (end_time, end_watts) in zip(
            self.watts, self.watts[1:]
        ):
            if start_time <= when <= end_time:
                span = (end_time - start_time).total_seconds()
                if span <= 0:
                    return end_watts
                ratio = (when - start_time).total_seconds() / span
                return start_watts + (end_watts - start_watts) * ratio
        return 0.0

    def energy_between(self, start: datetime, end: datetime) -> float:
        """Return forecast energy in kWh between two local datetimes.

        The watt curve is integrated with the trapezoidal rule. Segments that
        straddle the window edges are clipped, so a partial hour counts only
        for the part that is inside the window.
        """
        if end <= start or not self.watts:
            return 0.0

        total_wh = 0.0
        for (start_time, start_watts), (end_time, end_watts) in zip(
            self.watts, self.watts[1:]
        ):
            segment_start = max(start_time, start)
            segment_end = min(end_time, end)
            if segment_end <= segment_start:
                continue
            span = (end_time - start_time).total_seconds()
            if span <= 0:
                continue
            start_ratio = (segment_start - start_time).total_seconds() / span
            end_ratio = (segment_end - start_time).total_seconds() / span
            clipped_start = start_watts + (end_watts - start_watts) * start_ratio
            clipped_end = start_watts + (end_watts - start_watts) * end_ratio
            hours = (segment_end - segment_start).total_seconds() / 3600
            total_wh += (clipped_start + clipped_end) / 2 * hours
        return total_wh / 1000.0

    def energy_for_day(self, day: date) -> float | None:
        """Return the forecast energy for a whole local day in kWh."""
        raw = self.watt_hours_day.get(day.isoformat())
        if raw is not None:
            return raw / 1000.0
        if not self.watts:
            return None
        return self.energy_between(
            dt_util.start_of_local_day(day),
            dt_util.start_of_local_day(day + timedelta(days=1)),
        )

    def remaining_today(self, now: datetime) -> float:
        """Return the forecast energy from *now* until local midnight, in kWh."""
        end_of_day = dt_util.start_of_local_day(now.date() + timedelta(days=1))
        return self.energy_between(now, end_of_day)

    def curve(self, start: datetime, end: datetime) -> list[dict[str, Any]]:
        """Return the raw forecast points between two datetimes."""
        return [
            {"time": when.isoformat(), "watts": round(watts)}
            for when, watts in self.watts
            if start <= when <= end
        ]


def _parse_local_datetime(raw: Any) -> datetime | None:
    """Parse a Forecast.Solar timestamp, which is naive local site time."""
    if not isinstance(raw, str):
        return None
    parsed = dt_util.parse_datetime(raw)
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        # Forecast.Solar returns the local time of the configured site with
        # no offset. The site is expected to share Home Assistant's timezone.
        parsed = parsed.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
    return dt_util.as_local(parsed)


def _parse_watts(raw: Any) -> tuple[tuple[datetime, float], ...]:
    """Parse ``result.watts`` into a sorted tuple of points."""
    if not isinstance(raw, Mapping):
        return ()
    points: list[tuple[datetime, float]] = []
    for timestamp, value in raw.items():
        parsed = _parse_local_datetime(timestamp)
        numeric = as_float(value)
        if parsed is None or numeric is None:
            continue
        points.append((parsed, max(numeric, 0.0)))
    points.sort(key=lambda point: point[0])
    return tuple(points)


def _parse_payload(payload: Mapping[str, Any]) -> ForecastSolarData:
    """Validate a Forecast.Solar payload and convert it to data."""
    message = payload.get("message")
    if isinstance(message, Mapping):
        message_type = message.get("type")
        if message_type == "error":
            text = message.get("text") or "unknown error"
            raise UpdateFailed(f"Forecast.Solar reported an error: {text}")
        if message_type == "warning":
            _LOGGER.debug("Forecast.Solar warning: %s", message.get("text"))

    result = payload.get("result")
    if not isinstance(result, Mapping):
        raise UpdateFailed("Forecast.Solar response does not contain a result")

    watts = _parse_watts(result.get(_WATTS))
    if not watts:
        raise UpdateFailed("Forecast.Solar returned an empty forecast")

    watt_hours_day: dict[str, float] = {}
    raw_days = result.get(_WATT_HOURS_DAY)
    if isinstance(raw_days, Mapping):
        for key, value in raw_days.items():
            numeric = as_float(value)
            if isinstance(key, str) and numeric is not None:
                watt_hours_day[key] = numeric

    return ForecastSolarData(
        watts=watts,
        watt_hours_day=watt_hours_day,
        fetched_at=dt_util.now(dt_util.UTC),
    )


class PvPlannerCoordinator(DataUpdateCoordinator[ForecastSolarData]):
    """Poll the Forecast.Solar estimate endpoint once per interval."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        config: Mapping[str, Any],
    ) -> None:
        """Initialise the coordinator with the merged entry configuration."""
        poll_minutes = int(
            as_float(config.get(CONF_FORECAST_POLL_MINUTES))
            or DEFAULT_FORECAST_POLL_MINUTES
        )
        poll_minutes = max(poll_minutes, MIN_FORECAST_POLL_MINUTES)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{NAME} forecast",
            update_interval=timedelta(minutes=poll_minutes),
        )
        self.planner_config: dict[str, Any] = dict(config)

    def _build_url(self) -> str:
        """Build the Forecast.Solar estimate URL for the configured array."""
        config = self.planner_config
        return FORECAST_SOLAR_URL.format(
            latitude=f"{float(config.get(CONF_LATITUDE, 0.0)):.4f}",
            longitude=f"{float(config.get(CONF_LONGITUDE, 0.0)):.4f}",
            declination=round(float(config.get(CONF_DECLINATION, 0) or 0)),
            azimuth=round(float(config.get(CONF_AZIMUTH, 0) or 0)),
            kwp=f"{float(config.get(CONF_KWP, DEFAULT_KWP)):g}",
        )

    async def _async_update_data(self) -> ForecastSolarData:
        """Fetch and parse the current Forecast.Solar estimate."""
        url = self._build_url()
        session = async_get_clientsession(self.hass)
        try:
            async with asyncio.timeout(FORECAST_SOLAR_TIMEOUT):
                async with session.get(url) as response:
                    if response.status != 200:
                        raise UpdateFailed(
                            "Forecast.Solar request failed with HTTP status "
                            f"{response.status}"
                        )
                    payload = await response.json(content_type=None)
        except TimeoutError as err:
            raise UpdateFailed("Timed out while contacting Forecast.Solar") from err
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Error contacting Forecast.Solar: {err}") from err
        except ValueError as err:
            raise UpdateFailed("Forecast.Solar returned invalid JSON") from err

        if not isinstance(payload, Mapping):
            raise UpdateFailed("Forecast.Solar returned an unexpected payload")
        return _parse_payload(payload)
