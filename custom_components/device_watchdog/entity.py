"""Base entity for the Device Watchdog integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import DeviceWatchdogCoordinator


class DeviceWatchdogEntity(CoordinatorEntity[DeviceWatchdogCoordinator]):
    """Common base class for Device Watchdog entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: DeviceWatchdogCoordinator, key: str) -> None:
        """Initialise an entity bound to the watchdog coordinator."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry.entry_id)},
            name=coordinator.entry.title,
            manufacturer=MANUFACTURER,
            entry_type=DeviceEntryType.SERVICE,
        )
