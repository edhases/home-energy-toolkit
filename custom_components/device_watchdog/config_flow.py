"""Config flow for the Device Watchdog integration."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector

from .const import (
    CONF_ENTITIES,
    CONF_IGNORE_STARTUP,
    CONF_NOTIFY_SERVICE,
    CONF_OFFLINE_AFTER,
    CONF_PERSISTENT_NOTIFICATION,
    CONF_REPEAT,
    CONF_WATCH_UNKNOWN,
    DEFAULT_IGNORE_STARTUP,
    DEFAULT_OFFLINE_AFTER,
    DEFAULT_PERSISTENT_NOTIFICATION,
    DEFAULT_REPEAT,
    DEFAULT_WATCH_UNKNOWN,
    DOMAIN,
    MAX_MINUTES,
    NAME,
)
from .util import split_entity_list

_LOGGER = logging.getLogger(__name__)


def _build_schema(defaults: Mapping[str, Any]) -> vol.Schema:
    """Return the shared schema used by the user and options flows."""
    return vol.Schema(
        {
            vol.Required(
                CONF_ENTITIES, default=defaults.get(CONF_ENTITIES, "")
            ): selector.TextSelector(
                selector.TextSelectorConfig(multiline=True)
            ),
            vol.Required(
                CONF_OFFLINE_AFTER,
                default=defaults.get(CONF_OFFLINE_AFTER, DEFAULT_OFFLINE_AFTER),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1,
                    max=MAX_MINUTES,
                    step=1,
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_REPEAT,
                default=defaults.get(CONF_REPEAT, DEFAULT_REPEAT),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=5,
                    max=MAX_MINUTES,
                    step=1,
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Optional(
                CONF_NOTIFY_SERVICE,
                default=defaults.get(CONF_NOTIFY_SERVICE) or "",
            ): selector.TextSelector(),
            vol.Required(
                CONF_PERSISTENT_NOTIFICATION,
                default=defaults.get(
                    CONF_PERSISTENT_NOTIFICATION,
                    DEFAULT_PERSISTENT_NOTIFICATION,
                ),
            ): selector.BooleanSelector(),
            vol.Required(
                CONF_WATCH_UNKNOWN,
                default=defaults.get(
                    CONF_WATCH_UNKNOWN, DEFAULT_WATCH_UNKNOWN
                ),
            ): selector.BooleanSelector(),
            vol.Required(
                CONF_IGNORE_STARTUP,
                default=defaults.get(
                    CONF_IGNORE_STARTUP, DEFAULT_IGNORE_STARTUP
                ),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0,
                    max=MAX_MINUTES,
                    step=1,
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
        }
    )


def _current_values(entry: ConfigEntry) -> dict[str, Any]:
    """Return the current entry configuration in form representation."""

    def _value(key: str, default: Any) -> Any:
        value = entry.options.get(key, entry.data.get(key))
        return default if value is None else value

    return {
        CONF_ENTITIES: "\n".join(
            split_entity_list(_value(CONF_ENTITIES, []))
        ),
        CONF_OFFLINE_AFTER: _value(CONF_OFFLINE_AFTER, DEFAULT_OFFLINE_AFTER),
        CONF_REPEAT: _value(CONF_REPEAT, DEFAULT_REPEAT),
        CONF_NOTIFY_SERVICE: _value(CONF_NOTIFY_SERVICE, "") or "",
        CONF_PERSISTENT_NOTIFICATION: _value(
            CONF_PERSISTENT_NOTIFICATION,
            DEFAULT_PERSISTENT_NOTIFICATION,
        ),
        CONF_WATCH_UNKNOWN: _value(
            CONF_WATCH_UNKNOWN, DEFAULT_WATCH_UNKNOWN
        ),
        CONF_IGNORE_STARTUP: _value(
            CONF_IGNORE_STARTUP, DEFAULT_IGNORE_STARTUP
        ),
    }


async def _async_validate_input(
    hass: HomeAssistant, user_input: Mapping[str, Any]
) -> tuple[dict[str, Any] | None, dict[str, str], dict[str, str]]:
    """Validate user input and return cleaned data or errors."""
    raw_entities = user_input.get(CONF_ENTITIES)
    entity_ids = split_entity_list(raw_entities)
    if not entity_ids:
        return None, {"base": "no_entities"}, {}

    try:
        registry = er.async_get(hass)
        valid: list[str] = []
        invalid: list[str] = []
        for raw_entity_id in entity_ids:
            try:
                entity_id = cv.entity_id(raw_entity_id)
            except vol.Invalid:
                invalid.append(raw_entity_id)
                continue
            if (
                registry.async_get(entity_id) is None
                and hass.states.get(entity_id) is None
            ):
                invalid.append(raw_entity_id)
                continue
            valid.append(entity_id)

        if invalid:
            return (
                None,
                {"base": "invalid_entities"},
                {"invalid_entities": ", ".join(invalid)},
            )

        notify_service = str(
            user_input.get(CONF_NOTIFY_SERVICE) or ""
        ).strip()
        data: dict[str, Any] = {
            CONF_ENTITIES: valid,
            CONF_OFFLINE_AFTER: int(
                user_input.get(CONF_OFFLINE_AFTER, DEFAULT_OFFLINE_AFTER)
            ),
            CONF_REPEAT: int(user_input.get(CONF_REPEAT, DEFAULT_REPEAT)),
            CONF_NOTIFY_SERVICE: notify_service or None,
            CONF_PERSISTENT_NOTIFICATION: bool(
                user_input.get(
                    CONF_PERSISTENT_NOTIFICATION,
                    DEFAULT_PERSISTENT_NOTIFICATION,
                )
            ),
            CONF_WATCH_UNKNOWN: bool(
                user_input.get(CONF_WATCH_UNKNOWN, DEFAULT_WATCH_UNKNOWN)
            ),
            CONF_IGNORE_STARTUP: int(
                user_input.get(CONF_IGNORE_STARTUP, DEFAULT_IGNORE_STARTUP)
            ),
        }
    except Exception:
        _LOGGER.exception("Unexpected error validating Device Watchdog input")
        return None, {"base": "unknown"}, {}

    return data, {}, {}


class DeviceWatchdogConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial configuration of Device Watchdog."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask the user which entities to watch."""
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}

        if user_input is not None:
            data, errors, placeholders = await _async_validate_input(
                self.hass, user_input
            )
            if data is not None:
                return self.async_create_entry(title=NAME, data=data)

        return self.async_show_form(
            step_id="user",
            data_schema=_build_schema(user_input or {}),
            errors=errors,
            description_placeholders=placeholders,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> DeviceWatchdogOptionsFlow:
        """Return the options flow."""
        return DeviceWatchdogOptionsFlow()


class DeviceWatchdogOptionsFlow(OptionsFlow):
    """Handle options for an existing Device Watchdog entry."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the watched entities and notification settings."""
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}
        defaults: Mapping[str, Any]

        if user_input is not None:
            data, errors, placeholders = await _async_validate_input(
                self.hass, user_input
            )
            if data is not None:
                return self.async_create_entry(title="", data=data)
            defaults = user_input
        else:
            defaults = _current_values(self.config_entry)

        return self.async_show_form(
            step_id="init",
            data_schema=_build_schema(defaults),
            errors=errors,
            description_placeholders=placeholders,
        )
