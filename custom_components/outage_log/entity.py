"""Shared entity base for the Outage Log integration."""

from __future__ import annotations

from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .manager import OutageLogManager


class OutageLogEntity(Entity):
    """Common behaviour for Outage Log entities."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, manager: OutageLogManager, translation_key: str) -> None:
        """Initialize the entity."""
        self._manager = manager
        self._attr_translation_key = translation_key
        self._attr_unique_id = f"{manager.entry.entry_id}_{translation_key}"
        self._attr_device_info = manager.device_info

    async def async_added_to_hass(self) -> None:
        """Subscribe to runtime updates."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, self._manager.signal, self.async_write_ha_state
            )
        )
