"""Sensor platform for the Device Watchdog integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_OFFLINE,
    ATTR_WATCHED_COUNT,
    STATE_NONE,
)
from .coordinator import DeviceWatchdogCoordinator, WatchdogData
from .entity import DeviceWatchdogEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Device Watchdog sensors."""
    coordinator: DeviceWatchdogCoordinator = entry.runtime_data
    async_add_entities(
        [
            DevicesOfflineSensor(coordinator),
            OfflineDevicesSensor(coordinator),
        ]
    )


def _offline_attributes(data: WatchdogData) -> dict[str, Any]:
    """Return the shared attributes describing offline entities."""
    return {
        ATTR_OFFLINE: [
            {
                "entity_id": item.entity_id,
                "since": dt_util.as_utc(item.since).isoformat(),
                "minutes": item.minutes,
            }
            for item in data.offline
        ],
        ATTR_WATCHED_COUNT: data.watched_count,
    }


class DevicesOfflineSensor(DeviceWatchdogEntity, SensorEntity):
    """Number of watched entities that are currently offline."""

    _attr_icon = "mdi:lan-disconnect"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: DeviceWatchdogCoordinator) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, "devices_offline")

    @property
    def native_value(self) -> int:
        """Return the number of offline entities."""
        return self.coordinator.data.offline_count

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return details about the offline entities."""
        return _offline_attributes(self.coordinator.data)


class OfflineDevicesSensor(DeviceWatchdogEntity, SensorEntity):
    """Comma-separated list of offline entity names."""

    _attr_icon = "mdi:devices"

    def __init__(self, coordinator: DeviceWatchdogCoordinator) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, "offline_devices")

    @property
    def native_value(self) -> str:
        """Return the offline entity names, or ``none``."""
        return ", ".join(self.coordinator.data.offline_names) or STATE_NONE

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return details about the offline entities."""
        return _offline_attributes(self.coordinator.data)
