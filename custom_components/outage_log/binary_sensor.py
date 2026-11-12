"""Binary sensor platform for the Outage Log integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import OutageLogConfigEntry
from .entity import OutageLogEntity
from .manager import OutageLogManager


@dataclass(frozen=True, kw_only=True)
class OutageLogBinarySensorDescription(BinarySensorEntityDescription):
    """Describes an Outage Log binary sensor."""

    value_fn: Callable[[OutageLogManager], bool]


BINARY_SENSORS: tuple[OutageLogBinarySensorDescription, ...] = (
    OutageLogBinarySensorDescription(
        key="grid_outage",
        translation_key="grid_outage",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda manager: manager.grid_outage,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OutageLogConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Outage Log binary sensors."""
    manager = entry.runtime_data
    async_add_entities(
        OutageLogBinarySensor(manager, description) for description in BINARY_SENSORS
    )


class OutageLogBinarySensor(OutageLogEntity, BinarySensorEntity):
    """A binary sensor backed by the Outage Log manager."""

    entity_description: OutageLogBinarySensorDescription

    def __init__(
        self,
        manager: OutageLogManager,
        description: OutageLogBinarySensorDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(manager, description.translation_key or description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool:
        """Return True while the grid is absent."""
        return self.entity_description.value_fn(self._manager)
