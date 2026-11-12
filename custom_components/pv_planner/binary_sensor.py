"""Binary sensor platform for PV Planner."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .calculations import PlannerSnapshot, as_float, build_snapshot
from .const import CONF_SURPLUS_THRESHOLD_W, DEFAULT_SURPLUS_THRESHOLD_W
from .entity import PvPlannerEntity
from .forecast import PvPlannerCoordinator

if TYPE_CHECKING:
    from . import PvPlannerConfigEntry

type IsOnFn = Callable[["PvPlannerBinarySensor", PlannerSnapshot], bool | None]


def _surplus_available(
    entity: PvPlannerBinarySensor, snapshot: PlannerSnapshot
) -> bool | None:
    """Return True when the current surplus reaches the configured threshold."""
    if snapshot.surplus_w is None:
        return None
    threshold = as_float(
        entity.coordinator.planner_config.get(CONF_SURPLUS_THRESHOLD_W)
    )
    if threshold is None:
        threshold = DEFAULT_SURPLUS_THRESHOLD_W
    return snapshot.surplus_w >= threshold


def _reserve_ok(
    entity: PvPlannerBinarySensor, snapshot: PlannerSnapshot
) -> bool | None:
    """Return the battery reserve check result."""
    return snapshot.reserve_ok


@dataclass(frozen=True, kw_only=True)
class PvPlannerBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describes a PV Planner binary sensor."""

    is_on_fn: IsOnFn


BINARY_SENSOR_DESCRIPTIONS: Final[
    tuple[PvPlannerBinarySensorEntityDescription, ...]
] = (
    PvPlannerBinarySensorEntityDescription(
        key="surplus_available",
        translation_key="surplus_available",
        icon="mdi:solar-power",
        is_on_fn=_surplus_available,
    ),
    PvPlannerBinarySensorEntityDescription(
        key="battery_reserve_ok",
        translation_key="battery_reserve_ok",
        icon="mdi:battery-check",
        is_on_fn=_reserve_ok,
    ),
)


class PvPlannerBinarySensor(PvPlannerEntity, BinarySensorEntity):
    """A binary sensor whose value is derived by a description function."""

    entity_description: PvPlannerBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: PvPlannerCoordinator,
        entry: PvPlannerConfigEntry,
        description: PvPlannerBinarySensorEntityDescription,
    ) -> None:
        """Initialise the binary sensor from its description."""
        super().__init__(coordinator, entry)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"

    @property
    def is_on(self) -> bool | None:
        """Return True when the condition described by the sensor is met."""
        snapshot = build_snapshot(self.hass, self.coordinator.planner_config)
        return self.entity_description.is_on_fn(self, snapshot)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PvPlannerConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the PV Planner binary sensors."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        PvPlannerBinarySensor(coordinator, entry, description)
        for description in BINARY_SENSOR_DESCRIPTIONS
    )
