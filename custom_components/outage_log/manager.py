"""Runtime manager for the Outage Log integration."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import (
    Event,
    EventStateChangedData,
    HomeAssistant,
    State,
    callback,
)
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.storage import Store
from homeassistant.helpers.translation import async_get_translations
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_ENTRY_ID,
    CONF_BATTERY_CAPACITY_KWH,
    CONF_BATTERY_POWER_ENTITY,
    CONF_BATTERY_SOC_ENTITY,
    CONF_GRID_ENTITY,
    CONF_GRID_STATE_PRESENT,
    CONF_MIN_DURATION_SECONDS,
    CONF_NOTIFY_SERVICE,
    DEFAULT_BATTERY_CAPACITY_KWH,
    DEFAULT_GRID_STATE_PRESENT,
    DEFAULT_MIN_DURATION_SECONDS,
    DOMAIN,
    EVENT_OUTAGE_ENDED,
    EVENT_OUTAGE_STARTED,
    MAX_EPISODES,
    PERSISTENT_NOTIFICATION_THRESHOLD_SECONDS,
    SIGNAL_UPDATE,
    STORAGE_VERSION,
    TICK_INTERVAL_SECONDS,
)
from .models import Episode

_LOGGER = logging.getLogger(__name__)


class OutageLogManager:
    """Track grid outages and persist them as episodes."""

    def __init__(self, hass: HomeAssistant, entry: Any) -> None:
        """Initialize the manager."""
        self.hass = hass
        self.entry = entry

        config: dict[str, Any] = {**entry.data, **entry.options}
        self.grid_entity_id: str = config[CONF_GRID_ENTITY]
        self.grid_state_present: str = config.get(
            CONF_GRID_STATE_PRESENT, DEFAULT_GRID_STATE_PRESENT
        )
        self.battery_soc_entity_id: str | None = (
            config.get(CONF_BATTERY_SOC_ENTITY) or None
        )
        self.battery_power_entity_id: str | None = (
            config.get(CONF_BATTERY_POWER_ENTITY) or None
        )
        self.battery_capacity_kwh: float = _as_float(
            config.get(CONF_BATTERY_CAPACITY_KWH),
            DEFAULT_BATTERY_CAPACITY_KWH,
        )
        self.notify_service: str | None = config.get(CONF_NOTIFY_SERVICE) or None
        self.min_duration_seconds: int = max(
            0,
            int(
                _as_float(
                    config.get(CONF_MIN_DURATION_SECONDS),
                    DEFAULT_MIN_DURATION_SECONDS,
                )
            ),
        )

        self._store: Store = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")
        self._episodes: list[Episode] = []
        self._grid_present: bool | None = None
        self._outage_start: datetime | None = None
        self._outage_soc_start: float | None = None
        self._outage_recorded = False
        self._lock = asyncio.Lock()
        self._translations: dict[str, str] = {}
        self._unsub_state: Callable[[], None] | None = None
        self._unsub_tick: Callable[[], None] | None = None

    @property
    def signal(self) -> str:
        """Return the dispatcher signal used to update entities."""
        return SIGNAL_UPDATE.format(entry_id=self.entry.entry_id)

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information for the integration's entities."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.entry.entry_id)},
            name=self.entry.title,
            manufacturer="edhases",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://github.com/edhases/home-energy-toolkit",
        )

    @property
    def episodes(self) -> tuple[Episode, ...]:
        """Return all persisted episodes, oldest first."""
        return tuple(self._episodes)

    @property
    def grid_outage(self) -> bool:
        """Return True while the grid is absent."""
        return self._grid_present is False

    @property
    def current_episode(self) -> Episode | None:
        """Return the ongoing episode, including an unconfirmed candidate."""
        if self._outage_start is None:
            return None
        open_episode = self._open_episode
        if open_episode is not None:
            return open_episode
        return Episode(start=self._outage_start, soc_start=self._outage_soc_start)

    @property
    def event_summary(self) -> str:
        """Return the translated calendar event summary."""
        return self._t("grid_outage", "Grid outage")

    @property
    def _open_episode(self) -> Episode | None:
        """Return the persisted open episode, if any."""
        if self._episodes and self._episodes[-1].end is None:
            return self._episodes[-1]
        return None

    @property
    def calendar_episodes(self) -> tuple[Episode, ...]:
        """Return episodes for the calendar, including a pending candidate."""
        episodes = list(self._episodes)
        if self._outage_start is not None and self._open_episode is None:
            episodes.append(
                Episode(
                    start=self._outage_start,
                    soc_start=self._outage_soc_start,
                )
            )
        return tuple(episodes)

    async def async_setup(self) -> None:
        """Load persisted state and start listening for grid changes."""
        await self._async_load_translations()
        await self._async_load_episodes()
        await self._async_restore_state()

        self._unsub_state = async_track_state_change_event(
            self.hass, [self.grid_entity_id], self._async_grid_state_changed
        )
        self._unsub_tick = async_track_time_interval(
            self.hass,
            self._async_tick,
            timedelta(seconds=TICK_INTERVAL_SECONDS),
        )

    @callback
    def async_unload(self) -> None:
        """Stop listening for state changes and ticks."""
        if self._unsub_state is not None:
            self._unsub_state()
            self._unsub_state = None
        if self._unsub_tick is not None:
            self._unsub_tick()
            self._unsub_tick = None

    async def _async_load_translations(self) -> None:
        """Load the strings used in notifications and calendar events."""
        try:
            self._translations = await async_get_translations(
                self.hass,
                self.hass.config.language,
                "common",
                integrations={DOMAIN},
            )
        except Exception:  # noqa: BLE001 - translations must never break setup
            _LOGGER.debug("Could not load translations for %s", DOMAIN)
            self._translations = {}

    async def _async_load_episodes(self) -> None:
        """Load episodes from storage."""
        try:
            stored = await self._store.async_load()
        except Exception:
            _LOGGER.exception("Could not load stored outage episodes")
            stored = None

        if isinstance(stored, dict):
            stored = stored.get("episodes")

        episodes: list[Episode] = []
        if isinstance(stored, list):
            for item in stored:
                episode = Episode.from_dict(item)
                if episode is not None:
                    episodes.append(episode)

        episodes.sort(key=lambda episode: episode.start)
        trimmed = len(episodes) > MAX_EPISODES
        self._episodes = episodes[-MAX_EPISODES:]
        if trimmed:
            await self._async_save()

    async def _async_restore_state(self) -> None:
        """Reconcile the last episode with the current grid state at startup."""
        state = self.hass.states.get(self.grid_entity_id)
        self._grid_present = self._state_to_present(state)
        now = dt_util.utcnow()
        last = self._episodes[-1] if self._episodes else None

        if last is not None and last.end is None:
            if self._grid_present is False:
                # A reboot happened during the same outage: keep it open.
                self._outage_start = last.start
                self._outage_soc_start = last.soc_start
                self._outage_recorded = True
                _LOGGER.debug(
                    "Keeping outage episode that started at %s open after restart",
                    last.start,
                )
            else:
                # The grid came back while Home Assistant was not running.
                # The exact restoration time is unknown; use the start as fallback.
                last.end = last.start
                if last.soc_end is None:
                    last.soc_end = self._read_soc()
                await self._async_save()
                _LOGGER.debug(
                    "Closed stale outage episode at its start time: %s", last.start
                )
        elif self._grid_present is False:
            # An outage is already in progress but there is no open episode.
            self._outage_start = now
            self._outage_soc_start = self._read_soc()
            self._outage_recorded = False
            if self.min_duration_seconds == 0:
                await self._async_create_episode(
                    now,
                    notify=False,
                    fire_event=False,
                    soc_start=self._outage_soc_start,
                )

    @callback
    def _async_grid_state_changed(self, event: Event[EventStateChangedData]) -> None:
        """Handle a state change of the configured grid entity."""
        present = self._state_to_present(event.data.get("new_state"))
        if present is None or present == self._grid_present:
            return

        self._grid_present = present
        self.hass.async_create_task(self._async_process_grid_change(present))

    async def _async_process_grid_change(self, present: bool) -> None:
        """Process a confirmed grid transition."""
        async with self._lock:
            if present:
                await self._async_end_outage()
            else:
                await self._async_start_outage()

        async_dispatcher_send(self.hass, self.signal)

    async def _async_start_outage(self) -> None:
        """Start tracking a grid outage."""
        if self._outage_start is not None:
            return

        now = dt_util.utcnow()
        self._outage_start = now
        self._outage_soc_start = self._read_soc()
        self._outage_recorded = False
        _LOGGER.debug("Grid outage detected at %s", now)

        if self.min_duration_seconds == 0:
            await self._async_create_episode(now, soc_start=self._outage_soc_start)

    async def _async_end_outage(self) -> None:
        """Finish tracking a grid outage."""
        start = self._outage_start
        was_recorded = self._outage_recorded
        self._outage_start = None
        self._outage_soc_start = None
        self._outage_recorded = False

        if start is None or not was_recorded:
            # The grid returned before the minimum duration was reached.
            return

        episode = self._open_episode
        if episode is None:
            return

        now = dt_util.utcnow()
        episode.end = now
        episode.soc_end = self._read_soc()
        await self._async_save()

        duration = episode.duration_seconds or 0.0
        _LOGGER.debug(
            "Grid outage ended after %.1f seconds (started %s)", duration, start
        )

        self.hass.bus.async_fire(
            EVENT_OUTAGE_ENDED, self._event_data(episode, duration)
        )
        await self._async_notify_ended(episode)

        if duration >= PERSISTENT_NOTIFICATION_THRESHOLD_SECONDS:
            await self._async_create_persistent_notification(episode)

    async def _async_tick(self, _now: datetime) -> None:
        """Commit a candidate outage once it passes the minimum duration."""
        async with self._lock:
            if (
                self._outage_start is not None
                and not self._outage_recorded
                and self.min_duration_seconds > 0
            ):
                elapsed = (dt_util.utcnow() - self._outage_start).total_seconds()
                if elapsed >= self.min_duration_seconds:
                    await self._async_create_episode(
                        self._outage_start,
                        soc_start=self._outage_soc_start,
                    )

        async_dispatcher_send(self.hass, self.signal)

    async def _async_create_episode(
        self,
        start: datetime,
        *,
        notify: bool = True,
        fire_event: bool = True,
        soc_start: float | None = None,
    ) -> Episode | None:
        """Create and persist an episode, avoiding duplicates."""
        if self._episodes:
            last = self._episodes[-1]
            if last.end is None:
                # Never create a second open episode.
                self._outage_recorded = True
                return last
            if start <= last.end:
                # The transition happened at or before the previous end.
                self._outage_recorded = True
                return None

        episode = Episode(
            start=start,
            soc_start=soc_start if soc_start is not None else self._read_soc(),
        )
        self._episodes.append(episode)
        self._trim_episodes()
        self._outage_recorded = True
        await self._async_save()

        if fire_event:
            self.hass.bus.async_fire(
                EVENT_OUTAGE_STARTED, self._event_data(episode, 0.0)
            )
        if notify:
            await self._async_notify_started(episode)

        return episode

    async def _async_save(self) -> None:
        """Persist all episodes to storage."""
        self._trim_episodes()
        try:
            await self._store.async_save(
                [episode.as_dict() for episode in self._episodes]
            )
        except Exception:
            _LOGGER.exception("Could not save outage episodes")

    def _trim_episodes(self) -> None:
        """Drop the oldest episodes above the storage cap."""
        if len(self._episodes) > MAX_EPISODES:
            self._episodes = self._episodes[-MAX_EPISODES:]

    def _event_data(self, episode: Episode, duration: float) -> dict[str, Any]:
        """Build the event payload for start/end events."""
        return {
            ATTR_ENTRY_ID: self.entry.entry_id,
            "start": episode.start.isoformat(),
            "end": episode.end.isoformat() if episode.end is not None else None,
            "duration_seconds": round(duration, 1),
            "soc_start": episode.soc_start,
            "soc_end": episode.soc_end,
        }

    def _state_to_present(self, state: State | None) -> bool | None:
        """Translate a grid entity state into present/absent/unknown."""
        if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            return None
        return state.state == self.grid_state_present

    def _read_soc(self) -> float | None:
        """Read battery state of charge in percent."""
        return self._read_numeric(self.battery_soc_entity_id)

    def _read_power(self) -> float | None:
        """Read battery power in watts."""
        return self._read_numeric(self.battery_power_entity_id)

    def _read_numeric(self, entity_id: str | None) -> float | None:
        """Read a numeric sensor value, returning None when unavailable."""
        if entity_id is None:
            return None
        state = self.hass.states.get(entity_id)
        if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            return None
        try:
            return round(float(state.state), 1)
        except (TypeError, ValueError):
            return None

    def _now(self) -> datetime:
        """Return the current UTC time."""
        return dt_util.utcnow()

    def _overlap_seconds(
        self,
        episode: Episode,
        period_start: datetime,
        period_end: datetime,
        now: datetime,
    ) -> float:
        """Return the number of seconds an episode overlaps a period."""
        episode_end = episode.end or now
        if episode_end <= period_start or episode.start >= period_end:
            return 0.0
        return max(
            0.0,
            (
                min(episode_end, period_end) - max(episode.start, period_start)
            ).total_seconds(),
        )

    def _period_bounds(
        self,
    ) -> tuple[datetime, datetime, datetime, datetime, datetime]:
        """Return local today/month boundaries and the current time."""
        now = self._now()
        now_local = dt_util.as_local(now)
        today_start = dt_util.start_of_local_day(now_local)
        tomorrow_start = dt_util.start_of_local_day(now_local + timedelta(days=1))
        month_start = dt_util.start_of_local_day(now_local.replace(day=1))
        next_month = (now_local.replace(day=28) + timedelta(days=4)).replace(day=1)
        next_month_start = dt_util.start_of_local_day(next_month)
        return now, today_start, tomorrow_start, month_start, next_month_start

    @property
    def outages_today(self) -> int:
        """Return the number of outages started today."""
        _, today_start, tomorrow_start, _, _ = self._period_bounds()
        return sum(
            1
            for episode in self._episodes
            if today_start <= episode.start < tomorrow_start
        )

    @property
    def outages_month(self) -> int:
        """Return the number of outages started this month."""
        _, _, _, month_start, next_month_start = self._period_bounds()
        return sum(
            1
            for episode in self._episodes
            if month_start <= episode.start < next_month_start
        )

    @property
    def outage_time_today(self) -> float:
        """Return outage minutes overlapping today."""
        now, today_start, tomorrow_start, _, _ = self._period_bounds()
        seconds = sum(
            self._overlap_seconds(episode, today_start, tomorrow_start, now)
            for episode in self._episodes
        )
        return round(seconds / 60, 1)

    @property
    def outage_time_month(self) -> float:
        """Return outage hours overlapping the current month."""
        now, _, _, month_start, next_month_start = self._period_bounds()
        seconds = sum(
            self._overlap_seconds(episode, month_start, next_month_start, now)
            for episode in self._episodes
        )
        return round(seconds / 3600, 1)

    @property
    def last_outage_duration(self) -> float:
        """Return the duration of the most recent completed outage in minutes."""
        for episode in reversed(self._episodes):
            if episode.end is not None:
                return round((episode.duration_seconds or 0.0) / 60, 1)
        return 0.0

    @property
    def last_outage_started(self) -> datetime | None:
        """Return the start of the most recent episode."""
        if not self._episodes:
            return None
        return self._episodes[-1].start

    @property
    def current_outage_duration(self) -> float:
        """Return the current outage duration in minutes."""
        if self._outage_start is None:
            return 0.0
        return round(
            max(0.0, (self._now() - self._outage_start).total_seconds()) / 60,
            1,
        )

    def format_duration(self, seconds: float) -> str:
        """Format a duration using translated units."""
        if seconds < 60:
            return self._t(
                "duration_seconds",
                "{seconds} s",
                seconds=round(seconds),
            )
        if seconds < 3600:
            return self._t(
                "duration_minutes",
                "{minutes} min",
                minutes=round(seconds / 60),
            )
        return self._t(
            "duration_hours",
            "{hours} h",
            hours=round(seconds / 3600, 1),
        )

    def format_time(self, value: datetime) -> str:
        """Format a timestamp for notifications and descriptions."""
        return dt_util.as_local(value).strftime("%Y-%m-%d %H:%M")

    def _format_number(self, value: float) -> str:
        """Format a battery value without trailing zeros."""
        return f"{value:g}"

    def _energy_delta_kwh(self, episode: Episode) -> float | None:
        """Convert the state-of-charge delta to energy using the configured capacity."""
        if episode.soc_start is None or episode.soc_end is None:
            return None
        return round(
            (episode.soc_end - episode.soc_start) / 100 * self.battery_capacity_kwh,
            2,
        )

    def describe_episode(self, episode: Episode, now: datetime) -> str:
        """Build a translated calendar event description."""
        parts: list[str] = []
        end = episode.end
        duration = (
            (end - episode.start).total_seconds()
            if end is not None
            else (now - episode.start).total_seconds()
        )

        if end is None:
            parts.append(
                self._t(
                    "description_ongoing",
                    "Ongoing since {start}.",
                    start=self.format_time(episode.start),
                )
            )

        parts.append(
            self._t(
                "description_duration",
                "Duration: {duration}.",
                duration=self.format_duration(max(0.0, duration)),
            )
        )

        if episode.soc_start is not None and episode.soc_end is not None:
            parts.append(
                self._t(
                    "description_soc",
                    "Battery: {start}% at start, {end}% at end ({delta:+.1f} pp).",
                    start=self._format_number(episode.soc_start),
                    end=self._format_number(episode.soc_end),
                    delta=episode.soc_end - episode.soc_start,
                )
            )
            energy = self._energy_delta_kwh(episode)
            if energy is not None:
                parts.append(
                    self._t(
                        "description_energy",
                        "Estimated battery energy change: {energy:+.2f} kWh.",
                        energy=energy,
                    )
                )
        elif episode.soc_start is not None:
            parts.append(
                self._t(
                    "description_soc_start",
                    "Battery at start: {start}%.",
                    start=self._format_number(episode.soc_start),
                )
            )
        elif episode.soc_end is not None:
            parts.append(
                self._t(
                    "description_soc_end",
                    "Battery at end: {end}%.",
                    end=self._format_number(episode.soc_end),
                )
            )

        return " ".join(parts)

    async def _async_notify_started(self, episode: Episode) -> None:
        """Send a notification that an outage started."""
        message = self._t(
            "outage_started",
            "Grid power was lost at {time}.",
            time=self.format_time(episode.start),
        )

        soc = episode.soc_start if episode.soc_start is not None else self._read_soc()
        power = self._read_power()
        if soc is not None and power is not None:
            message = f"{message} " + self._t(
                "battery_soc_power",
                "Battery: {soc}% ({power} W).",
                soc=self._format_number(soc),
                power=self._format_number(power),
            )
        elif soc is not None:
            message = f"{message} " + self._t(
                "battery_soc",
                "Battery: {soc}%.",
                soc=self._format_number(soc),
            )
        elif power is not None:
            message = f"{message} " + self._t(
                "battery_power",
                "Battery power: {power} W.",
                power=self._format_number(power),
            )

        await self._async_send_notification(
            message,
            self._t(
                "outage_started_title",
                "Grid outage started",
            ),
        )

    async def _async_notify_ended(self, episode: Episode) -> None:
        """Send a notification that an outage ended."""
        duration = episode.duration_seconds or 0.0
        message = self._t(
            "outage_ended",
            "Grid power returned after {duration}.",
            duration=self.format_duration(duration),
        )

        if episode.soc_start is not None and episode.soc_end is not None:
            message = f"{message} " + self._t(
                "battery_delta",
                "Battery: {start}% → {end}% ({delta:+.1f} pp).",
                start=self._format_number(episode.soc_start),
                end=self._format_number(episode.soc_end),
                delta=episode.soc_end - episode.soc_start,
            )
            energy = self._energy_delta_kwh(episode)
            if energy is not None:
                message = f"{message} " + self._t(
                    "battery_energy",
                    "Estimated battery energy change: {energy:+.2f} kWh.",
                    energy=energy,
                )
        elif episode.soc_end is not None:
            message = f"{message} " + self._t(
                "battery_end",
                "Battery at restoration: {end}%.",
                end=self._format_number(episode.soc_end),
            )
        elif episode.soc_start is not None:
            message = f"{message} " + self._t(
                "battery_start",
                "Battery at outage start: {start}%.",
                start=self._format_number(episode.soc_start),
            )

        await self._async_send_notification(
            message,
            self._t(
                "outage_ended_title",
                "Grid power restored",
            ),
        )

    async def _async_send_notification(
        self, message: str, title: str | None = None
    ) -> None:
        """Call the configured notify service without raising on failure."""
        configured = (self.notify_service or "").strip()
        if not configured:
            return

        if "." in configured:
            domain, service = configured.split(".", 1)
        else:
            domain, service = "notify", configured

        if domain != "notify" or not service:
            _LOGGER.warning(
                "Invalid notify service %r; expected notify.<service>",
                configured,
            )
            return

        if not self.hass.services.has_service("notify", service):
            _LOGGER.warning(
                "Notify service %s is not available; skipping notification",
                configured,
            )
            return

        data: dict[str, Any] = {"message": message}
        if title:
            data["title"] = title

        try:
            await self.hass.services.async_call("notify", service, data, blocking=False)
        except Exception:
            _LOGGER.warning(
                "Could not send notification through %s",
                configured,
                exc_info=True,
            )

    async def _async_create_persistent_notification(self, episode: Episode) -> None:
        """Create a persistent notification for a long outage."""
        duration = episode.duration_seconds or 0.0
        message = self._t(
            "persistent_message",
            "The grid was unavailable for {duration}. The outage started at {time}.",
            duration=self.format_duration(duration),
            time=self.format_time(episode.start),
        )

        if episode.soc_start is not None and episode.soc_end is not None:
            message = f"{message} " + self._t(
                "battery_delta",
                "Battery: {start}% → {end}% ({delta:+.1f} pp).",
                start=self._format_number(episode.soc_start),
                end=self._format_number(episode.soc_end),
                delta=episode.soc_end - episode.soc_start,
            )
            energy = self._energy_delta_kwh(episode)
            if energy is not None:
                message = f"{message} " + self._t(
                    "battery_energy",
                    "Estimated battery energy change: {energy:+.2f} kWh.",
                    energy=energy,
                )

        try:
            await self.hass.services.async_call(
                "persistent_notification",
                "create",
                {
                    "title": self._t(
                        "persistent_title",
                        "Long grid outage",
                    ),
                    "message": message,
                    "notification_id": (
                        f"{DOMAIN}_{self.entry.entry_id}_"
                        f"{int(episode.start.timestamp())}"
                    ),
                },
                blocking=False,
            )
        except Exception:
            _LOGGER.warning(
                "Could not create persistent outage notification", exc_info=True
            )

    def _t(
        self,
        key: str,
        default: str,
        **parameters: Any,
    ) -> str:
        """Return a translated string with a safe English fallback."""
        template = self._translations.get(f"component.{DOMAIN}.common.{key}", default)
        try:
            return template.format(**parameters)
        except (KeyError, IndexError, ValueError):
            _LOGGER.debug("Invalid translation template for %s", key)
            try:
                return default.format(**parameters)
            except (KeyError, IndexError, ValueError):
                return default


def _as_float(value: Any, default: float) -> float:
    """Convert a config value to float with a fallback."""
    if value is None or isinstance(value, bool):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
