"""Shared entity base class for PV Planner."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, EventStateChangedData, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOCUMENTATION_URL, DOMAIN, NAME
from .forecast import PvPlannerCoordinator


class PvPlannerEntity(CoordinatorEntity[PvPlannerCoordinator]):
    """Base class that wires a PV Planner entity to the service device.

    Entities are named from their ``EntityDescription.translation_key``
    (``_attr_has_entity_name`` is enabled), so no user-facing name is ever
    hardcoded in Python.
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator: PvPlannerCoordinator, entry: ConfigEntry) -> None:
        """Initialise the entity and attach it to the integration device."""
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer=NAME,
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=DOCUMENTATION_URL,
        )

    async def async_added_to_hass(self) -> None:
        """Re-evaluate the derived values whenever a source entity changes.

        The forecast coordinator only polls once an hour, but the planner
        values are derived from live sensors. Without this listener a restart
        would leave the entities ``unknown`` until the next forecast poll.
        """
        await super().async_added_to_hass()
        entities = self._source_entities()
        if entities:
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass, entities, self._handle_source_event
                )
            )

    def _source_entities(self) -> list[str]:
        """Return the entity ids this integration reads from the config."""
        return [
            value
            for key, value in self.coordinator.planner_config.items()
            if key.endswith("_entity") and isinstance(value, str)
        ]

    @callback
    def _handle_source_event(self, event: Event[EventStateChangedData]) -> None:
        """Push a fresh state after one of the inputs changed."""
        self.async_write_ha_state()
