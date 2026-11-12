"""The Outage Log integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import PLATFORMS
from .manager import OutageLogManager

type OutageLogConfigEntry = ConfigEntry[OutageLogManager]


async def async_setup_entry(hass: HomeAssistant, entry: OutageLogConfigEntry) -> bool:
    """Set up Outage Log from a config entry."""
    manager = OutageLogManager(hass, entry)
    await manager.async_setup()
    entry.runtime_data = manager

    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except Exception:
        manager.async_unload()
        raise

    entry.async_on_unload(manager.async_unload)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: OutageLogConfigEntry) -> bool:
    """Unload an Outage Log config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
