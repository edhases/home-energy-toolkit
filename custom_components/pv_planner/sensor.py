"""Sensor platform for PV Planner."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING, Any, Final

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.translation import (
    async_translate_state,
    async_translate_state_attr,
)
from homeassistant.util import dt as dt_util

from .calculations import (
    PlannerSnapshot,
    as_float,
    build_snapshot,
)
from .const import (
    ADVICE_OPTIONS,
    CONF_BATTERY_CAPACITY_KWH,
    CONF_MIN_RESERVE_PERCENT,
    DEFAULT_BATTERY_CAPACITY_KWH,
    DEFAULT_MIN_RESERVE_PERCENT,
)
from .entity import PvPlannerEntity
from .forecast import PvPlannerCoordinator

if TYPE_CHECKING:
    from . import PvPlannerConfigEntry

type ValueFn = Callable[["PvPlannerSensor", PlannerSnapshot], Any]
type AttributesFn = Callable[
    ["PvPlannerSensor", PlannerSnapshot], Mapping[str, Any] | None
]


def _round_or_none(value: float | None, digits: int = 0) -> float | None:
    """Round a possibly missing value."""
    return None if value is None else round(value, digits)


def _forecast_today(entity: PvPlannerSensor, snapshot: PlannerSnapshot) -> float | None:
    data = entity.coordinator.data
    if data is None:
        return None
    value = data.energy_for_day(dt_util.now().date())
    return _round_or_none(value, 2)


def _forecast_tomorrow(
    entity: PvPlannerSensor, snapshot: PlannerSnapshot
) -> float | None:
    data = entity.coordinator.data
    if data is None:
        return None
    value = data.energy_for_day(dt_util.now().date() + timedelta(days=1))
    return _round_or_none(value, 2)


def _forecast_remaining(
    entity: PvPlannerSensor, snapshot: PlannerSnapshot
) -> float | None:
    data = entity.coordinator.data
    if data is None:
        return None
    return round(data.remaining_today(dt_util.now()), 2)


def _forecast_now(entity: PvPlannerSensor, snapshot: PlannerSnapshot) -> float | None:
    data = entity.coordinator.data
    if data is None:
        return None
    value = data.value_at(dt_util.now())
    return _round_or_none(value)


def _home_load(entity: PvPlannerSensor, snapshot: PlannerSnapshot) -> float | None:
    return _round_or_none(snapshot.home_load_w)


def _battery_charge(entity: PvPlannerSensor, snapshot: PlannerSnapshot) -> float | None:
    return _round_or_none(snapshot.battery_charge_w)


def _battery_remaining(
    entity: PvPlannerSensor, snapshot: PlannerSnapshot
) -> float | None:
    return _round_or_none(snapshot.battery_remaining_kwh, 2)


def _battery_reserve(entity: PvPlannerSensor, snapshot: PlannerSnapshot) -> float:
    return round(snapshot.battery_reserve_needed_kwh, 2)


def _power_surplus(entity: PvPlannerSensor, snapshot: PlannerSnapshot) -> float | None:
    return _round_or_none(snapshot.surplus_w)


def _energy_advice(entity: PvPlannerSensor, snapshot: PlannerSnapshot) -> str:
    return snapshot.advice


def _forecast_attributes(
    entity: PvPlannerSensor, snapshot: PlannerSnapshot
) -> Mapping[str, Any] | None:
    """Return the raw curve for today and tomorrow, ready for ApexCharts."""
    data = entity.coordinator.data
    if data is None:
        return None
    today = dt_util.now().date()
    return {
        "curve": data.curve(
            dt_util.start_of_local_day(today),
            dt_util.start_of_local_day(today + timedelta(days=2)),
        ),
        "last_update": data.fetched_at.isoformat(),
        "provider": data.provider,
    }


def _surplus_attributes(
    entity: PvPlannerSensor, snapshot: PlannerSnapshot
) -> Mapping[str, Any]:
    return {
        "pv_now": _round_or_none(snapshot.pv_now_w),
        "home_load": _round_or_none(snapshot.home_load_w),
        "battery_charge": _round_or_none(snapshot.battery_charge_w),
        "import_w": _round_or_none(snapshot.import_w),
        "export_w": _round_or_none(snapshot.export_w),
    }


def _reserve_attributes(
    entity: PvPlannerSensor, snapshot: PlannerSnapshot
) -> Mapping[str, Any]:
    """Explain how the required reserve is calculated."""
    config = entity.coordinator.planner_config
    capacity = as_float(config.get(CONF_BATTERY_CAPACITY_KWH))
    if capacity is None:
        capacity = DEFAULT_BATTERY_CAPACITY_KWH
    reserve_percent = as_float(config.get(CONF_MIN_RESERVE_PERCENT))
    if reserve_percent is None:
        reserve_percent = DEFAULT_MIN_RESERVE_PERCENT
    explanation = async_translate_state_attr(
        entity.hass,
        "night_consumption",
        entity.platform_data.domain,
        entity.platform_data.platform_name,
        entity.translation_key,
        entity.device_class,
        "explanation",
    )
    return {
        "explanation": explanation,
        "night_consumption_kwh": round(snapshot.battery_reserve_needed_kwh, 2),
        "min_reserve_percent": reserve_percent,
        "battery_capacity_kwh": capacity,
        "reserve_floor_kwh": round(
            snapshot.battery_reserve_needed_kwh + reserve_percent / 100.0 * capacity,
            2,
        ),
    }


def _advice_attributes(
    entity: PvPlannerSensor, snapshot: PlannerSnapshot
) -> Mapping[str, Any] | None:
    """Return the human readable version of the advice state."""
    advice = entity.native_value
    if not isinstance(advice, str):
        return None
    return {
        "advice_text": async_translate_state(
            entity.hass,
            advice,
            entity.platform_data.domain,
            entity.platform_data.platform_name,
            entity.translation_key,
            entity.device_class,
        )
    }


@dataclass(frozen=True, kw_only=True)
class PvPlannerSensorEntityDescription(SensorEntityDescription):
    """Describes a PV Planner sensor."""

    value_fn: ValueFn
    attributes_fn: AttributesFn | None = None


SENSOR_DESCRIPTIONS: Final[tuple[PvPlannerSensorEntityDescription, ...]] = (
    PvPlannerSensorEntityDescription(
        key="pv_forecast_today",
        translation_key="pv_forecast_today",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=2,
        icon="mdi:solar-power-variant",
        value_fn=_forecast_today,
        attributes_fn=_forecast_attributes,
    ),
    PvPlannerSensorEntityDescription(
        key="pv_forecast_tomorrow",
        translation_key="pv_forecast_tomorrow",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=2,
        icon="mdi:solar-power-variant-outline",
        value_fn=_forecast_tomorrow,
    ),
    PvPlannerSensorEntityDescription(
        key="pv_forecast_remaining_today",
        translation_key="pv_forecast_remaining_today",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=2,
        icon="mdi:solar-power-variant",
        value_fn=_forecast_remaining,
    ),
    PvPlannerSensorEntityDescription(
        key="pv_forecast_now",
        translation_key="pv_forecast_now",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        icon="mdi:solar-power",
        value_fn=_forecast_now,
    ),
    PvPlannerSensorEntityDescription(
        key="home_load_power",
        translation_key="home_load_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        icon="mdi:home-lightning-bolt",
        value_fn=_home_load,
    ),
    PvPlannerSensorEntityDescription(
        key="battery_charge_power",
        translation_key="battery_charge_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        icon="mdi:battery-charging",
        value_fn=_battery_charge,
    ),
    PvPlannerSensorEntityDescription(
        key="battery_remaining_energy",
        translation_key="battery_remaining_energy",
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        icon="mdi:battery-heart-variant",
        value_fn=_battery_remaining,
    ),
    PvPlannerSensorEntityDescription(
        key="battery_reserve_needed",
        translation_key="battery_reserve_needed",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        icon="mdi:battery-lock",
        value_fn=_battery_reserve,
        attributes_fn=_reserve_attributes,
    ),
    PvPlannerSensorEntityDescription(
        key="power_surplus",
        translation_key="power_surplus",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        icon="mdi:transmission-tower-export",
        value_fn=_power_surplus,
        attributes_fn=_surplus_attributes,
    ),
    PvPlannerSensorEntityDescription(
        key="energy_advice",
        translation_key="energy_advice",
        device_class=SensorDeviceClass.ENUM,
        options=list(ADVICE_OPTIONS),
        icon="mdi:lightbulb-on-outline",
        value_fn=_energy_advice,
        attributes_fn=_advice_attributes,
    ),
)


class PvPlannerSensor(PvPlannerEntity, SensorEntity):
    """A sensor whose value is derived by a description function."""

    entity_description: PvPlannerSensorEntityDescription
    # The forecast curve is large and not worth recording in the database.
    _unrecorded_attributes = frozenset({"curve"})

    def __init__(
        self,
        coordinator: PvPlannerCoordinator,
        entry: PvPlannerConfigEntry,
        description: PvPlannerSensorEntityDescription,
    ) -> None:
        """Initialise the sensor from its description."""
        super().__init__(coordinator, entry)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"

    @property
    def snapshot(self) -> PlannerSnapshot:
        """Return the derived values for the current moment."""
        return build_snapshot(self.hass, self.coordinator.planner_config)

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""
        return self.entity_description.value_fn(self, self.snapshot)

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return the description specific attributes."""
        attributes_fn = self.entity_description.attributes_fn
        if attributes_fn is None:
            return None
        return attributes_fn(self, self.snapshot)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PvPlannerConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the PV Planner sensors."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        PvPlannerSensor(coordinator, entry, description)
        for description in SENSOR_DESCRIPTIONS
    )
