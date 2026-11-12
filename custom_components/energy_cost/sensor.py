"""Sensor platform for the Energy Cost integration."""

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
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    MANUFACTURER,
    MODEL,
    TARIFF_STATES,
)
from .coordinator import EnergyCostCoordinator, EnergyCostData

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class EnergyCostSensorDescription(SensorEntityDescription):
    """Describes an Energy Cost sensor."""

    value_fn: Callable[[EnergyCostData], float | str | None]


MONEY_SENSORS: tuple[EnergyCostSensorDescription, ...] = (
    EnergyCostSensorDescription(
        key="cost_period",
        translation_key="cost_period",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:cash",
        suggested_display_precision=2,
        value_fn=lambda data: round(data.cost_period, 4),
    ),
    EnergyCostSensorDescription(
        key="import_cost_period",
        translation_key="import_cost_period",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:cash",
        suggested_display_precision=2,
        value_fn=lambda data: round(data.import_cost_period, 4),
    ),
    EnergyCostSensorDescription(
        key="export_revenue_period",
        translation_key="export_revenue_period",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:cash",
        suggested_display_precision=2,
        value_fn=lambda data: round(data.export_revenue_period, 4),
    ),
    EnergyCostSensorDescription(
        key="pv_saved_period",
        translation_key="pv_saved_period",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:cash",
        suggested_display_precision=2,
        value_fn=lambda data: round(data.pv_saved_period, 4),
    ),
    EnergyCostSensorDescription(
        key="cost_today",
        translation_key="cost_today",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:cash",
        suggested_display_precision=2,
        value_fn=lambda data: round(data.cost_today, 4),
    ),
    EnergyCostSensorDescription(
        key="cost_month",
        translation_key="cost_month",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:cash",
        suggested_display_precision=2,
        value_fn=lambda data: round(data.cost_month, 4),
    ),
    EnergyCostSensorDescription(
        key="cost_total",
        translation_key="cost_total",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:cash",
        suggested_display_precision=2,
        value_fn=lambda data: round(data.cost_total, 4),
    ),
)

OTHER_SENSORS: tuple[EnergyCostSensorDescription, ...] = (
    EnergyCostSensorDescription(
        key="current_price",
        translation_key="current_price",
        icon="mdi:cash",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=4,
        value_fn=lambda data: round(data.current_price, 4),
    ),
    EnergyCostSensorDescription(
        key="tariff_now",
        translation_key="tariff_now",
        device_class=SensorDeviceClass.ENUM,
        icon="mdi:clock-outline",
        options=list(TARIFF_STATES),
        value_fn=lambda data: data.tariff_now,
    ),
)

SENSOR_DESCRIPTIONS: tuple[EnergyCostSensorDescription, ...] = (
    *MONEY_SENSORS,
    *OTHER_SENSORS,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Energy Cost sensors from a config entry."""
    coordinator: EnergyCostCoordinator = entry.runtime_data
    async_add_entities(
        EnergyCostSensor(coordinator, entry, description)
        for description in SENSOR_DESCRIPTIONS
    )


class EnergyCostSensor(CoordinatorEntity[EnergyCostCoordinator], SensorEntity):
    """Representation of an Energy Cost sensor."""

    _attr_has_entity_name = True
    entity_description: EnergyCostSensorDescription

    def __init__(
        self,
        coordinator: EnergyCostCoordinator,
        entry: ConfigEntry,
        description: EnergyCostSensorDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_translation_key = description.translation_key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer=MANUFACTURER,
            model=MODEL,
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def native_value(self) -> float | str | None:
        """Return the current sensor value."""
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the unit, using the configured currency for money sensors."""
        data = self.coordinator.data
        currency = data.currency if data is not None else self.coordinator.currency

        if self.entity_description.device_class == SensorDeviceClass.MONETARY:
            return currency
        if self.entity_description.key == "current_price":
            return f"{currency}/kWh"
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra attributes."""
        data = self.coordinator.data
        if data is None:
            return None

        if self.entity_description.device_class == SensorDeviceClass.MONETARY:
            attributes: dict[str, Any] = {
                "currency": data.currency,
                "tariff_mode": data.tariff_mode,
            }
            if self.entity_description.key == "cost_period":
                attributes["period_start"] = data.period_start.isoformat()
            return attributes

        if self.entity_description.key == "current_price":
            return {
                "currency": data.currency,
                "tariff_mode": data.tariff_mode,
                "tariff_now": data.tariff_now,
            }

        if self.entity_description.key == "tariff_now":
            return {
                "currency": data.currency,
                "tariff_mode": data.tariff_mode,
            }

        return None
