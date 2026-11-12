"""Config flow for the Energy Cost integration."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import time as dt_time
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
    OptionsFlowWithReload,
)
from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT
from homeassistant.core import HomeAssistant
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
    TimeSelector,
)

from .const import (
    CONF_CURRENCY,
    CONF_EXPORT_ENERGY_ENTITY,
    CONF_EXPORT_PRICE,
    CONF_IMPORT_ENERGY_ENTITY,
    CONF_MONTH_START_DAY,
    CONF_NIGHT_END,
    CONF_NIGHT_START,
    CONF_PRICE_DAY,
    CONF_PRICE_NIGHT,
    CONF_PRICE_SINGLE,
    CONF_PV_ENERGY_ENTITY,
    CONF_TARIFF_MODE,
    DEFAULT_CONFIG,
    DEFAULT_CURRENCY,
    DEFAULT_EXPORT_PRICE,
    DEFAULT_MONTH_START_DAY,
    DEFAULT_NIGHT_END,
    DEFAULT_NIGHT_START,
    DEFAULT_PRICE_DAY,
    DEFAULT_PRICE_NIGHT,
    DEFAULT_PRICE_SINGLE,
    DEFAULT_TARIFF_MODE,
    DOMAIN,
    ENERGY_UNIT_FACTORS,
    TARIFF_MODES,
)
from .tariff import format_clock, parse_clock

OPTIONAL_ENERGY_ENTITIES = (CONF_EXPORT_ENERGY_ENTITY, CONF_PV_ENERGY_ENTITY)


def _build_schema(defaults: Mapping[str, Any]) -> vol.Schema:
    """Build the configuration schema shared by the user and options flows."""
    entity_selector = EntitySelector(EntitySelectorConfig(domain="sensor"))
    price_selector = NumberSelector(
        NumberSelectorConfig(
            min=0,
            max=1000,
            step=0.01,
            mode=NumberSelectorMode.BOX,
        )
    )
    import_default = defaults.get(CONF_IMPORT_ENERGY_ENTITY)
    fields: dict[Any, Any] = {}
    if isinstance(import_default, str) and import_default:
        fields[
            vol.Required(CONF_IMPORT_ENERGY_ENTITY, default=import_default)
        ] = entity_selector
    else:
        fields[vol.Required(CONF_IMPORT_ENERGY_ENTITY)] = entity_selector

    for key in OPTIONAL_ENERGY_ENTITIES:
        default_entity = defaults.get(key)
        if isinstance(default_entity, str) and default_entity:
            fields[
                vol.Optional(
                    key, description={"suggested_value": default_entity}
                )
            ] = entity_selector
        else:
            fields[vol.Optional(key)] = entity_selector

    fields.update(
        {
            vol.Required(
                CONF_TARIFF_MODE,
                default=defaults.get(CONF_TARIFF_MODE, DEFAULT_TARIFF_MODE),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=TARIFF_MODES,
                    translation_key="tariff_mode",
                )
            ),
            vol.Required(
                CONF_PRICE_SINGLE,
                default=defaults.get(CONF_PRICE_SINGLE, DEFAULT_PRICE_SINGLE),
            ): price_selector,
            vol.Required(
                CONF_PRICE_DAY,
                default=defaults.get(CONF_PRICE_DAY, DEFAULT_PRICE_DAY),
            ): price_selector,
            vol.Required(
                CONF_PRICE_NIGHT,
                default=defaults.get(CONF_PRICE_NIGHT, DEFAULT_PRICE_NIGHT),
            ): price_selector,
            vol.Required(
                CONF_NIGHT_START,
                default=_time_default(
                    defaults.get(CONF_NIGHT_START), DEFAULT_NIGHT_START
                ),
            ): TimeSelector(),
            vol.Required(
                CONF_NIGHT_END,
                default=_time_default(
                    defaults.get(CONF_NIGHT_END), DEFAULT_NIGHT_END
                ),
            ): TimeSelector(),
            vol.Required(
                CONF_EXPORT_PRICE,
                default=defaults.get(CONF_EXPORT_PRICE, DEFAULT_EXPORT_PRICE),
            ): price_selector,
            vol.Required(
                CONF_CURRENCY,
                default=defaults.get(CONF_CURRENCY, DEFAULT_CURRENCY),
            ): TextSelector(TextSelectorConfig(type=TextSelectorType.TEXT)),
            vol.Required(
                CONF_MONTH_START_DAY,
                default=defaults.get(
                    CONF_MONTH_START_DAY, DEFAULT_MONTH_START_DAY
                ),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=1,
                    max=28,
                    step=1,
                    mode=NumberSelectorMode.BOX,
                )
            ),
        }
    )
    return vol.Schema(fields)


def _time_default(value: Any, fallback: str) -> Any:
    """Return a time object suitable as a selector default."""
    default = parse_clock(fallback, dt_time(0, 0))
    return parse_clock(value, default)


def _validate_entities(
    hass: HomeAssistant, user_input: Mapping[str, Any]
) -> dict[str, str]:
    """Validate that the selected entities are energy sensors in a known unit."""
    errors: dict[str, str] = {}
    for key in (CONF_IMPORT_ENERGY_ENTITY, *OPTIONAL_ENERGY_ENTITIES):
        entity_id = user_input.get(key)
        if not entity_id:
            if key == CONF_IMPORT_ENERGY_ENTITY:
                errors[key] = "invalid_entity"
            continue

        if not isinstance(entity_id, str) or not entity_id.startswith("sensor."):
            errors[key] = "invalid_entity"
            continue

        state = hass.states.get(entity_id)
        if state is None:
            errors[key] = "invalid_entity"
            continue

        unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
        if not unit or str(unit).strip() not in ENERGY_UNIT_FACTORS:
            errors[key] = "invalid_unit"

    return errors


def _normalize_input(user_input: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize selector output for permanent storage."""
    data: dict[str, Any] = dict(user_input)

    tariff_mode = data.get(CONF_TARIFF_MODE)
    data[CONF_TARIFF_MODE] = (
        tariff_mode if tariff_mode in TARIFF_MODES else DEFAULT_TARIFF_MODE
    )

    for key, default in (
        (CONF_PRICE_SINGLE, DEFAULT_PRICE_SINGLE),
        (CONF_PRICE_DAY, DEFAULT_PRICE_DAY),
        (CONF_PRICE_NIGHT, DEFAULT_PRICE_NIGHT),
        (CONF_EXPORT_PRICE, DEFAULT_EXPORT_PRICE),
    ):
        try:
            value = float(data.get(key, default))
        except (TypeError, ValueError):
            value = default
        data[key] = max(0.0, value)

    data[CONF_NIGHT_START] = format_clock(
        data.get(CONF_NIGHT_START), DEFAULT_NIGHT_START
    )
    data[CONF_NIGHT_END] = format_clock(data.get(CONF_NIGHT_END), DEFAULT_NIGHT_END)

    try:
        month_start_day = int(data.get(CONF_MONTH_START_DAY, DEFAULT_MONTH_START_DAY))
    except (TypeError, ValueError):
        month_start_day = DEFAULT_MONTH_START_DAY
    data[CONF_MONTH_START_DAY] = max(1, min(28, month_start_day))

    currency = str(data.get(CONF_CURRENCY) or "").strip()
    data[CONF_CURRENCY] = currency or DEFAULT_CURRENCY

    for key in OPTIONAL_ENERGY_ENTITIES:
        if not data.get(key):
            data.pop(key, None)

    return data


class EnergyCostConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial configuration of Energy Cost."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the user step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = _validate_entities(self.hass, user_input)
            if not errors:
                data = _normalize_input(user_input)
                await self.async_set_unique_id(data[CONF_IMPORT_ENERGY_ENTITY])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title="Energy Cost", data=data)

        defaults = dict(DEFAULT_CONFIG)
        if user_input is not None:
            defaults.update(user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=_build_schema(defaults),
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return EnergyCostOptionsFlow()


class EnergyCostOptionsFlow(OptionsFlowWithReload):
    """Handle options for an existing Energy Cost entry."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = _validate_entities(self.hass, user_input)
            if not errors:
                return self.async_create_entry(
                    title="", data=_normalize_input(user_input)
                )

        defaults = {**self.config_entry.data, **self.config_entry.options}
        if user_input is not None:
            defaults.update(user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=_build_schema(defaults),
            errors=errors,
        )
