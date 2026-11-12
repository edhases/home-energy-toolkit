"""Shared entity base class for PV Planner."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
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
