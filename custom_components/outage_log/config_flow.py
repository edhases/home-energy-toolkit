"""Config and options flow for the Outage Log integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    OptionsFlowWithReload,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    CONF_BATTERY_CAPACITY_KWH,
    CONF_BATTERY_POWER_ENTITY,
    CONF_BATTERY_SOC_ENTITY,
    CONF_GRID_ENTITY,
    CONF_GRID_STATE_PRESENT,
    CONF_MIN_DURATION_SECONDS,
    CONF_NOTIFY_SERVICE,
    DEFAULT_BATTERY_CAPACITY_KWH,
    DEFAULT_GRID_STATE_PRESENT,
    DEFAULT_MIN_DURATION_SECONDS,
    DOMAIN,
    GRID_STATE_ABSENT,
    GRID_STATE_PRESENT,
)


def _build_schema() -> vol.Schema:
    """Return the shared config/options schema."""
    return vol.Schema(
        {
            vol.Required(CONF_GRID_ENTITY): EntitySelector(
                EntitySelectorConfig(domain="binary_sensor")
            ),
            vol.Required(
                CONF_GRID_STATE_PRESENT,
                default=DEFAULT_GRID_STATE_PRESENT,
            ): SelectSelector(
                SelectSelectorConfig(
                    options=[GRID_STATE_PRESENT, GRID_STATE_ABSENT],
                    translation_key="grid_state_present",
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(CONF_BATTERY_SOC_ENTITY): EntitySelector(
                EntitySelectorConfig(domain="sensor")
            ),
            vol.Optional(CONF_BATTERY_POWER_ENTITY): EntitySelector(
                EntitySelectorConfig(domain="sensor")
            ),
            vol.Optional(
                CONF_BATTERY_CAPACITY_KWH,
                default=DEFAULT_BATTERY_CAPACITY_KWH,
            ): NumberSelector(
                NumberSelectorConfig(
                    min=0.1,
                    max=1000,
                    step=0.1,
                    mode=NumberSelectorMode.BOX,
                    unit_of_measurement="kWh",
                )
            ),
            vol.Optional(CONF_NOTIFY_SERVICE): TextSelector(
                TextSelectorConfig(type=TextSelectorType.TEXT)
            ),
            vol.Optional(
                CONF_MIN_DURATION_SECONDS,
                default=DEFAULT_MIN_DURATION_SECONDS,
            ): NumberSelector(
                NumberSelectorConfig(
                    min=0,
                    max=86400,
                    step=1,
                    mode=NumberSelectorMode.BOX,
                    unit_of_measurement="s",
                )
            ),
        }
    )


def _validate_entity(hass: HomeAssistant, entity_id: Any, domain: str) -> bool:
    """Return True when the entity exists and has the expected domain."""
    if not isinstance(entity_id, str) or not entity_id.startswith(f"{domain}."):
        return False
    return hass.states.get(entity_id) is not None


def _validate_input(hass: HomeAssistant, user_input: dict[str, Any]) -> dict[str, str]:
    """Validate entity references in config or options input."""
    valid = _validate_entity(hass, user_input.get(CONF_GRID_ENTITY), "binary_sensor")
    for key in (CONF_BATTERY_SOC_ENTITY, CONF_BATTERY_POWER_ENTITY):
        entity_id = user_input.get(key)
        if entity_id and not _validate_entity(hass, entity_id, "sensor"):
            valid = False

    if not valid:
        return {"base": "invalid_entity"}
    return {}


def _to_float(value: Any, default: float) -> float:
    """Convert an input value to float."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_input(user_input: dict[str, Any]) -> dict[str, Any]:
    """Normalize form input into config entry data."""
    present_state = user_input.get(CONF_GRID_STATE_PRESENT, DEFAULT_GRID_STATE_PRESENT)
    if present_state not in (GRID_STATE_PRESENT, GRID_STATE_ABSENT):
        present_state = DEFAULT_GRID_STATE_PRESENT

    return {
        CONF_GRID_ENTITY: user_input[CONF_GRID_ENTITY],
        CONF_GRID_STATE_PRESENT: present_state,
        CONF_BATTERY_SOC_ENTITY: user_input.get(CONF_BATTERY_SOC_ENTITY) or None,
        CONF_BATTERY_POWER_ENTITY: user_input.get(CONF_BATTERY_POWER_ENTITY) or None,
        CONF_BATTERY_CAPACITY_KWH: _to_float(
            user_input.get(CONF_BATTERY_CAPACITY_KWH),
            DEFAULT_BATTERY_CAPACITY_KWH,
        ),
        CONF_NOTIFY_SERVICE: (
            str(user_input.get(CONF_NOTIFY_SERVICE, "")).strip() or None
        ),
        CONF_MIN_DURATION_SECONDS: max(
            0,
            int(
                _to_float(
                    user_input.get(CONF_MIN_DURATION_SECONDS),
                    DEFAULT_MIN_DURATION_SECONDS,
                )
            ),
        ),
    }


class OutageLogConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the Outage Log config flow."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> OutageLogOptionsFlow:
        """Return the options flow for this entry."""
        return OutageLogOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> Any:
        """Handle the initial configuration step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = _validate_input(self.hass, user_input)
            if not errors:
                data = _normalize_input(user_input)
                await self.async_set_unique_id(
                    data[CONF_GRID_ENTITY], raise_on_progress=False
                )
                self._abort_if_unique_id_configured()
                # Keep the entry title in English so generated entity_ids stay
                # stable and readable; all entity names are translated.
                return self.async_create_entry(title="Outage Log", data=data)

        schema = _build_schema()
        if user_input is not None:
            schema = self.add_suggested_values_to_schema(schema, user_input)

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)


class OutageLogOptionsFlow(OptionsFlowWithReload):
    """Handle Outage Log options."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> Any:
        """Manage the integration options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = _validate_input(self.hass, user_input)
            if not errors:
                return self.async_create_entry(
                    title="", data=_normalize_input(user_input)
                )

        current = {**self.config_entry.data, **self.config_entry.options}
        schema = self.add_suggested_values_to_schema(_build_schema(), current)
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
