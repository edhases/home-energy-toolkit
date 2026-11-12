"""The PV Planner integration.

PV Planner turns a PV + battery + grid setup into decision sensors. It never
switches devices itself; automations decide what to do with the surplus.
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .forecast import PvPlannerCoordinator

PLATFORMS: tuple[Platform, ...] = (Platform.SENSOR, Platform.BINARY_SENSOR)


@dataclass(slots=True)
class PvPlannerRuntimeData:
    """Runtime data stored on the config entry."""

    coordinator: PvPlannerCoordinator


type PvPlannerConfigEntry = ConfigEntry[PvPlannerRuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: PvPlannerConfigEntry) -> bool:
    """Set up PV Planner from a config entry."""
    coordinator = PvPlannerCoordinator(
        hass,
        entry,
        {**entry.data, **entry.options},
    )
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = PvPlannerRuntimeData(coordinator=coordinator)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: PvPlannerConfigEntry) -> bool:
    """Unload a PV Planner config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
