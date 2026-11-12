"""Offline tracking and notifications for the Device Watchdog integration."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_FRIENDLY_NAME, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store
from homeassistant.helpers.translation import async_get_translations
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CONF_ENTITIES,
    CONF_IGNORE_STARTUP,
    CONF_NOTIFY_SERVICE,
    CONF_OFFLINE_AFTER,
    CONF_PERSISTENT_NOTIFICATION,
    CONF_REPEAT,
    CONF_WATCH_UNKNOWN,
    DEFAULT_IGNORE_STARTUP,
    DEFAULT_NOTIFICATIONS,
    DEFAULT_OFFLINE_AFTER,
    DEFAULT_PERSISTENT_NOTIFICATION,
    DEFAULT_REPEAT,
    DEFAULT_WATCH_UNKNOWN,
    DOMAIN,
    NOTIFICATION_CATEGORY,
    STORE_SAVE_DELAY,
    STORE_VERSION,
    UPDATE_INTERVAL,
)
from .util import split_entity_list

_LOGGER = logging.getLogger(__name__)

_PERSISTENT_NOTIFICATION_DOMAIN = "persistent_notification"

NOTIFICATION_PREFIX = f"component.{DOMAIN}.{NOTIFICATION_CATEGORY}."


@dataclass(frozen=True, slots=True)
class WatchdogSettings:
    """Resolved settings for one config entry."""

    entities: tuple[str, ...]
    offline_after: timedelta
    repeat: timedelta
    notify_service: str | None
    persistent_notification: bool
    watch_unknown: bool
    ignore_startup: timedelta

    @classmethod
    def from_entry(cls, entry: ConfigEntry) -> WatchdogSettings:
        """Build settings from a config entry (options win over data)."""

        def _value(key: str, default: Any) -> Any:
            value = entry.options.get(key, entry.data.get(key))
            return default if value is None else value

        entities = split_entity_list(_value(CONF_ENTITIES, []))
        notify_service = _value(CONF_NOTIFY_SERVICE, "")
        return cls(
            entities=tuple(entities),
            offline_after=timedelta(
                minutes=int(_value(CONF_OFFLINE_AFTER, DEFAULT_OFFLINE_AFTER))
            ),
            repeat=timedelta(minutes=int(_value(CONF_REPEAT, DEFAULT_REPEAT))),
            notify_service=str(notify_service).strip() or None,
            persistent_notification=bool(
                _value(
                    CONF_PERSISTENT_NOTIFICATION,
                    DEFAULT_PERSISTENT_NOTIFICATION,
                )
            ),
            watch_unknown=bool(_value(CONF_WATCH_UNKNOWN, DEFAULT_WATCH_UNKNOWN)),
            ignore_startup=timedelta(
                minutes=int(_value(CONF_IGNORE_STARTUP, DEFAULT_IGNORE_STARTUP))
            ),
        )


@dataclass(frozen=True, slots=True)
class OfflineEntity:
    """A watched entity that is currently offline."""

    entity_id: str
    name: str
    since: datetime
    minutes: int


@dataclass(frozen=True, slots=True)
class WatchdogData:
    """Snapshot of the current watchdog state."""

    watched_count: int
    offline: tuple[OfflineEntity, ...] = ()

    @property
    def offline_count(self) -> int:
        """Return the number of offline entities."""
        return len(self.offline)

    @property
    def offline_names(self) -> list[str]:
        """Return the friendly names of the offline entities."""
        return [item.name for item in self.offline]


@dataclass(slots=True)
class _TrackedEntity:
    """Mutable per-entity bookkeeping."""

    entity_id: str
    offline_since: datetime | None = None
    last_notified: datetime | None = None
    notified: bool = False


class DeviceWatchdogCoordinator(DataUpdateCoordinator[WatchdogData]):
    """Poll the state machine and send offline/recovery notifications."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialise the watchdog for a config entry."""
        self.entry = entry
        self.settings = WatchdogSettings.from_entry(entry)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.title}",
            update_interval=UPDATE_INTERVAL,
        )
        self._store: Store[dict[str, Any]] = Store(
            hass,
            STORE_VERSION,
            f"{DOMAIN}.{entry.entry_id}",
        )
        self._tracked: dict[str, _TrackedEntity] = {
            entity_id: _TrackedEntity(entity_id)
            for entity_id in self.settings.entities
        }
        self._started_at = dt_util.utcnow()
        self._grace_until = self._started_at + self.settings.ignore_startup
        self._translations: dict[str, str] = {}
        self._translations_loaded = False
        self.data = WatchdogData(watched_count=len(self._tracked))

    @property
    def entry_id(self) -> str:
        """Return the config entry id."""
        return self.entry.entry_id

    def _notification_id(self, entity_id: str) -> str:
        """Return a stable persistent notification id for an entity."""
        return f"{DOMAIN}_{self.entry.entry_id}_{entity_id.replace('.', '_')}"

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    async def async_load_store(self) -> None:
        """Restore offline timestamps and notification history from disk."""
        try:
            stored = await self._store.async_load()
        except Exception:
            _LOGGER.warning(
                "Could not restore Device Watchdog state for %s",
                self.entry.title,
                exc_info=True,
            )
            return

        if not isinstance(stored, dict):
            return
        entities = stored.get("entities")
        if not isinstance(entities, dict):
            return

        now = dt_util.utcnow()
        for entity_id, tracked in self._tracked.items():
            raw = entities.get(entity_id)
            if not isinstance(raw, dict):
                continue
            tracked.offline_since = _parse_timestamp(raw.get("offline_since"), now)
            tracked.last_notified = _parse_timestamp(raw.get("last_notified"), now)
            tracked.notified = bool(raw.get("notified")) and (
                tracked.offline_since is not None
            )

        _LOGGER.debug(
            "Restored watchdog state for %s (%s watched entities)",
            self.entry.title,
            len(self._tracked),
        )

    async def async_save_state(self) -> None:
        """Write the current tracking state to disk immediately."""
        try:
            await self._store.async_save(self._data_to_save())
        except Exception:
            _LOGGER.warning(
                "Could not save Device Watchdog state for %s",
                self.entry.title,
                exc_info=True,
            )

    def _async_schedule_save(self) -> None:
        """Schedule a delayed write of the tracking state."""
        self._store.async_delay_save(self._data_to_save, STORE_SAVE_DELAY)

    def _data_to_save(self) -> dict[str, Any]:
        """Return a JSON-serialisable snapshot for the store."""
        return {
            "entities": {
                tracked.entity_id: {
                    "offline_since": _format_timestamp(tracked.offline_since),
                    "last_notified": _format_timestamp(tracked.last_notified),
                    "notified": tracked.notified,
                }
                for tracked in self._tracked.values()
            }
        }

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------
    async def _async_update_data(self) -> WatchdogData:
        """Evaluate every watched entity and notify when needed."""
        now = dt_util.utcnow()
        notifications_allowed = (
            not self.hass.is_stopping and now >= self._grace_until
        )
        offline: list[OfflineEntity] = []
        dirty = False
        registry = er.async_get(self.hass)

        for entity_id, tracked in self._tracked.items():
            state = self.hass.states.get(entity_id)
            name = _friendly_name(entity_id, state, registry)

            if not self._is_offline(state):
                if tracked.offline_since is not None:
                    duration = now - tracked.offline_since
                    notified = tracked.notified
                    await self._async_dismiss(entity_id)
                    if notified and notifications_allowed:
                        await self._async_send_recovery(name, entity_id, duration)
                    _reset_tracking(tracked)
                    dirty = True
                continue

            if tracked.offline_since is None:
                tracked.offline_since = now
                tracked.last_notified = None
                tracked.notified = False
                dirty = True

            duration = now - tracked.offline_since
            offline.append(
                OfflineEntity(
                    entity_id=entity_id,
                    name=name,
                    since=tracked.offline_since,
                    minutes=max(int(duration.total_seconds() // 60), 0),
                )
            )

            if not notifications_allowed:
                continue

            if not tracked.notified:
                if duration >= self.settings.offline_after:
                    await self._async_send_offline(
                        name, entity_id, duration, repeat=False
                    )
                    tracked.notified = True
                    tracked.last_notified = now
                    dirty = True
            elif (
                tracked.last_notified is not None
                and now - tracked.last_notified >= self.settings.repeat
            ):
                await self._async_send_offline(
                    name, entity_id, duration, repeat=True
                )
                tracked.last_notified = now
                dirty = True

        if dirty:
            self._async_schedule_save()

        offline.sort(key=lambda item: (-item.minutes, item.entity_id))
        return WatchdogData(
            watched_count=len(self._tracked),
            offline=tuple(offline),
        )

    def _is_offline(self, state: State | None) -> bool:
        """Return True when the entity counts as offline."""
        if state is None:
            return True
        if state.state == STATE_UNAVAILABLE:
            return True
        return self.settings.watch_unknown and state.state == STATE_UNKNOWN

    async def async_reset(self) -> None:
        """Forget all tracking data and notification history."""
        for tracked in self._tracked.values():
            await self._async_dismiss(tracked.entity_id)
            _reset_tracking(tracked)
        await self.async_save_state()
        await self.async_refresh()

    # ------------------------------------------------------------------
    # Notifications
    # ------------------------------------------------------------------
    async def _async_send_offline(
        self,
        name: str,
        entity_id: str,
        duration: timedelta,
        *,
        repeat: bool,
    ) -> None:
        """Send an offline (or repeated offline) notification."""
        duration_text = await self._async_format_duration(duration)
        translations = await self._async_notification_strings()
        key = "repeat" if repeat else "offline"
        title = self._translate(
            translations,
            f"{key}.title",
            name=name,
        )
        message = self._translate(
            translations,
            f"{key}.message",
            name=name,
            entity_id=entity_id,
            duration=duration_text,
        )
        await self._async_notify(
            title, message, self._notification_id(entity_id)
        )
        _LOGGER.debug("Reported %s as offline for %s", entity_id, duration_text)

    async def _async_send_recovery(
        self, name: str, entity_id: str, duration: timedelta
    ) -> None:
        """Send a recovery notification after an offline period."""
        duration_text = await self._async_format_duration(duration)
        translations = await self._async_notification_strings()
        title = self._translate(translations, "recovered.title", name=name)
        message = self._translate(
            translations,
            "recovered.message",
            name=name,
            entity_id=entity_id,
            duration=duration_text,
        )
        await self._async_notify(
            title, message, self._notification_id(entity_id)
        )
        _LOGGER.debug("Reported %s as back online", entity_id)

    async def _async_notify(
        self, title: str, message: str, notification_id: str
    ) -> None:
        """Deliver a notification through all configured channels."""
        if self.settings.persistent_notification:
            try:
                await self.hass.services.async_call(
                    _PERSISTENT_NOTIFICATION_DOMAIN,
                    "create",
                    {
                        "title": title,
                        "message": message,
                        "notification_id": notification_id,
                    },
                    blocking=False,
                )
            except Exception:
                _LOGGER.warning(
                    "Could not create persistent notification %s",
                    notification_id,
                    exc_info=True,
                )

        if not self.settings.notify_service:
            return

        domain, separator, service = self.settings.notify_service.partition(".")
        if not domain or not separator or not service:
            _LOGGER.warning(
                "Invalid notify service %r for %s; expected 'notify.<service>'",
                self.settings.notify_service,
                self.entry.title,
            )
            return
        if not self.hass.services.has_service(domain, service):
            _LOGGER.warning(
                "Notify service %s is not available; skipping notification",
                self.settings.notify_service,
            )
            return

        try:
            await self.hass.services.async_call(
                domain,
                service,
                {"title": title, "message": message},
                blocking=False,
            )
        except Exception:
            _LOGGER.warning(
                "Failed to send notification through %s",
                self.settings.notify_service,
                exc_info=True,
            )

    async def _async_dismiss(self, entity_id: str) -> None:
        """Remove the persistent notification for an entity, if any."""
        try:
            await self.hass.services.async_call(
                _PERSISTENT_NOTIFICATION_DOMAIN,
                "dismiss",
                {"notification_id": self._notification_id(entity_id)},
                blocking=False,
            )
        except Exception:
            _LOGGER.debug(
                "Could not dismiss notification for %s", entity_id, exc_info=True
            )

    async def _async_notification_strings(self) -> Mapping[str, str]:
        """Return (and cache) the notifications translation category."""
        if self._translations_loaded:
            return self._translations
        self._translations_loaded = True
        try:
            self._translations = await async_get_translations(
                self.hass,
                self.hass.config.language,
                NOTIFICATION_CATEGORY,
                [DOMAIN],
            )
        except Exception:
            _LOGGER.warning(
                "Could not load Device Watchdog notification translations",
                exc_info=True,
            )
            self._translations = {}
        return self._translations

    def _translate(
        self,
        translations: Mapping[str, str],
        key: str,
        **values: Any,
    ) -> str:
        """Format a translated notification string with an English fallback."""
        default = DEFAULT_NOTIFICATIONS[key]
        template = translations.get(f"{NOTIFICATION_PREFIX}{key}", default)
        try:
            return template.format(**values)
        except (KeyError, IndexError, ValueError):
            _LOGGER.debug("Invalid translation template for notifications.%s", key)
            return default.format(**values)

    async def _async_format_duration(self, duration: timedelta) -> str:
        """Return a compact, translated duration such as ``2 h 5 min``."""
        translations = await self._async_notification_strings()
        total_minutes = max(int(duration.total_seconds() // 60), 0)
        days, remainder = divmod(total_minutes, 1440)
        hours, minutes = divmod(remainder, 60)

        day_unit = self._translate(translations, "units.days")
        hour_unit = self._translate(translations, "units.hours")
        minute_unit = self._translate(translations, "units.minutes")

        if days:
            parts = [f"{days} {day_unit}"]
            if hours:
                parts.append(f"{hours} {hour_unit}")
            return " ".join(parts)
        if hours:
            parts = [f"{hours} {hour_unit}"]
            if minutes:
                parts.append(f"{minutes} {minute_unit}")
            return " ".join(parts)
        return f"{total_minutes} {minute_unit}"


def _reset_tracking(tracked: _TrackedEntity) -> None:
    """Clear all tracking fields of an entity."""
    tracked.offline_since = None
    tracked.last_notified = None
    tracked.notified = False


def _friendly_name(
    entity_id: str,
    state: State | None,
    registry: er.EntityRegistry,
) -> str:
    """Return the best available friendly name for an entity."""
    if state is not None:
        name = state.attributes.get(ATTR_FRIENDLY_NAME)
        if isinstance(name, str) and name:
            return name
    entry = registry.async_get(entity_id)
    if entry is not None:
        return entry.name or entry.original_name or entity_id
    return entity_id


def _format_timestamp(value: datetime | None) -> str | None:
    """Return an ISO timestamp for storage, or None."""
    if value is None:
        return None
    return dt_util.as_utc(value).isoformat()


def _parse_timestamp(value: Any, now: datetime) -> datetime | None:
    """Parse a stored ISO timestamp, ignoring invalid or future values."""
    if not isinstance(value, str):
        return None
    parsed = dt_util.parse_datetime(value)
    if parsed is None:
        return None
    parsed = dt_util.as_utc(parsed)
    if parsed > now:
        # Clock changed or corrupted value; restart the timer instead.
        return None
    return parsed
