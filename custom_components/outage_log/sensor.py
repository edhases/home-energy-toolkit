"""Sensor platform for the Outage Log integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import OutageLogConfigEntry
from .entity import OutageLogEntity
from .manager import OutageLogManager


@dataclass(frozen=True, kw_only=True)
class OutageLogSensorDescription(SensorEntityDescription):
    """Describes an Outage Log sensor and how to compute its value."""

    value_fn: Callable[[OutageLogManager], Any]


SENSORS: tuple[OutageLogSensorDescription, ...] = (
    OutageLogSensorDescription(
        key="outages_today",
        translation_key="outages_today",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda manager: manager.outages_today,
    ),
    OutageLogSensorDescription(
        key="outages_month",
        translation_key="outages_month",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda manager: manager.outages_month,
    ),
    OutageLogSensorDescription(
        key="outage_time_today",
        translation_key="outage_time_today",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda manager: manager.outage_time_today,
    ),
    OutageLogSensorDescription(
        key="outage_time_month",
        translation_key="outage_time_month",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda manager: manager.outage_time_month,
    ),
    OutageLogSensorDescription(
        key="last_outage_duration",
        translation_key="last_outage_duration",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda manager: manager.last_outage_duration,
    ),
    OutageLogSensorDescription(
        key="last_outage_started",
        translation_key="last_outage_started",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda manager: manager.last_outage_started,
    ),
    OutageLogSensorDescription(
        key="current_outage_duration",
        translation_key="current_outage_duration",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda manager: manager.current_outage_duration,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OutageLogConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Outage Log sensors."""
    manager = entry.runtime_data
    async_add_entities(OutageLogSensor(manager, description) for description in SENSORS)


class OutageLogSensor(OutageLogEntity, SensorEntity):
    """A sensor backed by the Outage Log manager."""

    entity_description: OutageLogSensorDescription

    def __init__(
        self,
        manager: OutageLogManager,
        description: OutageLogSensorDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(manager, description.translation_key or description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        """Return the current value."""
        return self.entity_description.value_fn(self._manager)
