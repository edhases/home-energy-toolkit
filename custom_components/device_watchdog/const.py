"""Constants for the Device Watchdog integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "device_watchdog"
NAME: Final = "Device Watchdog"
MANUFACTURER: Final = "Home Energy Toolkit"

PLATFORMS: Final = [Platform.SENSOR, Platform.BINARY_SENSOR]

CONF_ENTITIES: Final = "entities"
CONF_OFFLINE_AFTER: Final = "offline_after_minutes"
CONF_REPEAT: Final = "repeat_minutes"
CONF_NOTIFY_SERVICE: Final = "notify_service"
CONF_PERSISTENT_NOTIFICATION: Final = "persistent_notification"
CONF_WATCH_UNKNOWN: Final = "watch_unknown"
CONF_IGNORE_STARTUP: Final = "ignore_startup_minutes"

DEFAULT_OFFLINE_AFTER: Final = 10
DEFAULT_REPEAT: Final = 120
DEFAULT_IGNORE_STARTUP: Final = 5
DEFAULT_PERSISTENT_NOTIFICATION: Final = True
DEFAULT_WATCH_UNKNOWN: Final = False

MAX_MINUTES: Final = 10080

UPDATE_INTERVAL: Final = timedelta(seconds=30)
STORE_VERSION: Final = 1
STORE_SAVE_DELAY: Final = 10

ATTR_OFFLINE: Final = "offline"
ATTR_WATCHED_COUNT: Final = "watched_count"
ATTR_ENTRY_ID: Final = "entry_id"

SERVICE_CHECK_NOW: Final = "check_now"
SERVICE_RESET: Final = "reset"

STATE_NONE: Final = "none"

NOTIFICATION_CATEGORY: Final = "notifications"

# English fallbacks, used if translation files cannot be loaded.  The same
# strings live in strings.json/translations and are normally used instead.
DEFAULT_NOTIFICATIONS: Final[dict[str, str]] = {
    "offline.title": "Device offline: {name}",
    "offline.message": "{name} ({entity_id}) has been offline for {duration}.",
    "repeat.title": "Device still offline: {name}",
    "repeat.message": "{name} ({entity_id}) is still offline after {duration}.",
    "recovered.title": "Device back online: {name}",
    "recovered.message": (
        "{name} ({entity_id}) is back online after {duration} offline."
    ),
    "units.days": "d",
    "units.hours": "h",
    "units.minutes": "min",
}
