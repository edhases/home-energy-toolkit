"""The Energy Cost integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import PLATFORMS
from .coordinator import EnergyCostCoordinator

EnergyCostConfigEntry = ConfigEntry[EnergyCostCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: EnergyCostConfigEntry) -> bool:
    """Set up Energy Cost from a config entry."""
    coordinator = EnergyCostCoordinator(hass, entry)
    await coordinator.async_setup()

    entry.runtime_data = coordinator

    await coordinator.async_config_entry_first_refresh()
    coordinator.async_start_listening()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: EnergyCostConfigEntry) -> bool:
    """Unload an Energy Cost config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_shutdown()
    return unloaded
