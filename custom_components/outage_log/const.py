"""Constants for the Outage Log integration."""

from __future__ import annotations

from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "outage_log"

PLATFORMS: Final = (
    Platform.BINARY_SENSOR,
    Platform.CALENDAR,
    Platform.SENSOR,
)

STORAGE_VERSION: Final = 1
MAX_EPISODES: Final = 1000
TICK_INTERVAL_SECONDS: Final = 30

CONF_GRID_ENTITY: Final = "grid_entity"
CONF_GRID_STATE_PRESENT: Final = "grid_state_present"
CONF_BATTERY_SOC_ENTITY: Final = "battery_soc_entity"
CONF_BATTERY_POWER_ENTITY: Final = "battery_power_entity"
CONF_BATTERY_CAPACITY_KWH: Final = "battery_capacity_kwh"
CONF_NOTIFY_SERVICE: Final = "notify_service"
CONF_MIN_DURATION_SECONDS: Final = "min_duration_seconds"

DEFAULT_GRID_STATE_PRESENT: Final = "on"
DEFAULT_BATTERY_CAPACITY_KWH: Final = 5.0
DEFAULT_MIN_DURATION_SECONDS: Final = 30

GRID_STATE_PRESENT: Final = "on"
GRID_STATE_ABSENT: Final = "off"

EVENT_OUTAGE_STARTED: Final = f"{DOMAIN}_outage_started"
EVENT_OUTAGE_ENDED: Final = f"{DOMAIN}_outage_ended"

SIGNAL_UPDATE: Final = f"{DOMAIN}_update_{{entry_id}}"

ATTR_ENTRY_ID: Final = "entry_id"

PERSISTENT_NOTIFICATION_THRESHOLD_SECONDS: Final = 5 * 60
