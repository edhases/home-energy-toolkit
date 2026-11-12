"""The Device Watchdog integration."""

from __future__ import annotations

import asyncio
import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import (
    ATTR_ENTRY_ID,
    DOMAIN,
    PLATFORMS,
    SERVICE_CHECK_NOW,
    SERVICE_RESET,
)
from .coordinator import DeviceWatchdogCoordinator

_LOGGER = logging.getLogger(__name__)

type DeviceWatchdogConfigEntry = ConfigEntry[DeviceWatchdogCoordinator]

SERVICE_SCHEMA = vol.Schema({vol.Optional(ATTR_ENTRY_ID): cv.string})


def _coordinators(hass: HomeAssistant) -> dict[str, DeviceWatchdogCoordinator]:
    """Return the mapping of loaded coordinators by entry id."""
    return hass.data.setdefault(DOMAIN, {})


def _resolve_coordinators(
    hass: HomeAssistant, entry_id: str | None
) -> list[DeviceWatchdogCoordinator]:
    """Return the targeted coordinators, raising if an id is unknown."""
    coordinators = _coordinators(hass)
    if entry_id:
        coordinator = coordinators.get(entry_id)
        if coordinator is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="entry_not_found",
                translation_placeholders={"entry_id": entry_id},
            )
        return [coordinator]
    return list(coordinators.values())


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the Device Watchdog services."""
    _coordinators(hass)
    hass.services.async_register(
        DOMAIN,
        SERVICE_CHECK_NOW,
        _async_handle_check_now,
        schema=SERVICE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_RESET,
        _async_handle_reset,
        schema=SERVICE_SCHEMA,
    )
    return True


async def async_setup_entry(
    hass: HomeAssistant, entry: DeviceWatchdogConfigEntry
) -> bool:
    """Set up Device Watchdog from a config entry."""
    coordinator = DeviceWatchdogCoordinator(hass, entry)
    await coordinator.async_load_store()

    entry.runtime_data = coordinator
    await coordinator.async_config_entry_first_refresh()

    _coordinators(hass)[entry.entry_id] = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: DeviceWatchdogConfigEntry
) -> bool:
    """Unload a Device Watchdog config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(
        entry, PLATFORMS
    )
    if unload_ok:
        coordinator = getattr(entry, "runtime_data", None)
        if coordinator is not None:
            await coordinator.async_save_state()
        _coordinators(hass).pop(entry.entry_id, None)
    return unload_ok


async def _async_update_listener(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def _async_handle_check_now(call: ServiceCall) -> None:
    """Force an immediate evaluation for one or all entries."""
    coordinators = _resolve_coordinators(
        call.hass, call.data.get(ATTR_ENTRY_ID)
    )
    if not coordinators:
        _LOGGER.debug("No Device Watchdog entries to check")
        return
    await asyncio.gather(
        *(coordinator.async_refresh() for coordinator in coordinators)
    )


async def _async_handle_reset(call: ServiceCall) -> None:
    """Clear offline tracking and notification history."""
    coordinators = _resolve_coordinators(
        call.hass, call.data.get(ATTR_ENTRY_ID)
    )
    if not coordinators:
        _LOGGER.debug("No Device Watchdog entries to reset")
        return
    await asyncio.gather(
        *(coordinator.async_reset() for coordinator in coordinators)
    )
