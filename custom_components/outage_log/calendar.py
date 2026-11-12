"""Calendar platform for the Outage Log integration."""

from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import OutageLogConfigEntry
from .entity import OutageLogEntity
from .manager import OutageLogManager
from .models import Episode


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OutageLogConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Outage Log calendar."""
    async_add_entities([OutageLogCalendar(entry.runtime_data)])


class OutageLogCalendar(OutageLogEntity, CalendarEntity):
    """Calendar containing recorded grid outage episodes."""

    def __init__(self, manager: OutageLogManager) -> None:
        """Initialize the calendar."""
        super().__init__(manager, "grid_outages")

    @property
    def event(self) -> CalendarEvent | None:
        """Return the current or next outage event."""
        now = dt_util.utcnow()

        current = self._manager.current_episode
        if current is not None:
            return self._build_event(current, now)

        upcoming = [
            episode
            for episode in self._manager.calendar_episodes
            if episode.start > now
        ]
        if upcoming:
            return self._build_event(
                min(upcoming, key=lambda episode: episode.start), now
            )

        return None

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        """Return episodes overlapping the requested range."""
        start_date = _as_aware(start_date)
        end_date = _as_aware(end_date)
        now = dt_util.utcnow()
        events: list[CalendarEvent] = []

        for episode in self._manager.calendar_episodes:
            event_end = episode.end or now
            if event_end <= start_date or episode.start >= end_date:
                continue
            if event_end <= episode.start:
                # Skip zero-length fallback episodes; calendars need a range.
                continue
            events.append(self._build_event(episode, now))

        events.sort(key=lambda event: event.start)
        return events

    def _build_event(self, episode: Episode, now: datetime) -> CalendarEvent:
        """Build a calendar event from an episode."""
        end = episode.end or now
        if end <= episode.start:
            end = episode.start + timedelta(seconds=1)

        return CalendarEvent(
            summary=self._manager.event_summary,
            start=episode.start,
            end=end,
            description=self._manager.describe_episode(episode, now),
            uid=(f"{self._manager.entry.entry_id}_{int(episode.start.timestamp())}"),
        )


def _as_aware(value: datetime) -> datetime:
    """Return a timezone-aware datetime."""
    if value.tzinfo is None:
        return value.replace(tzinfo=dt_util.UTC)
    return value
