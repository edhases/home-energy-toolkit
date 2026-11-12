"""Binary sensor platform for the Device Watchdog integration."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import DeviceWatchdogCoordinator
from .entity import DeviceWatchdogEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Device Watchdog binary sensor."""
    coordinator: DeviceWatchdogCoordinator = entry.runtime_data
    async_add_entities([AnyDeviceOfflineBinarySensor(coordinator)])


class AnyDeviceOfflineBinarySensor(DeviceWatchdogEntity, BinarySensorEntity):
    """On when at least one watched entity is offline."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_icon = "mdi:alert-circle-outline"

    def __init__(self, coordinator: DeviceWatchdogCoordinator) -> None:
        """Initialise the binary sensor."""
        super().__init__(coordinator, "any_device_offline")

    @property
    def is_on(self) -> bool:
        """Return True when any watched entity is offline."""
        return self.coordinator.data.offline_count > 0
