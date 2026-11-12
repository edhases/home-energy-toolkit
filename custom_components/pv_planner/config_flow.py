"""Config and options flow for PV Planner."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT,
    CONF_LATITUDE,
    CONF_LONGITUDE,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector

from .const import (
    BATTERY_SIGN_OPTIONS,
    CONF_AZIMUTH,
    CONF_BATTERY_CAPACITY_KWH,
    CONF_BATTERY_POWER_ENTITY,
    CONF_BATTERY_SIGN,
    CONF_BATTERY_SOC_ENTITY,
    CONF_DECLINATION,
    CONF_FORECAST_POLL_MINUTES,
    CONF_GRID_ENTITY,
    CONF_GRID_SIGN,
    CONF_KWP,
    CONF_MIN_RESERVE_PERCENT,
    CONF_NIGHT_CONSUMPTION_KWH,
    CONF_PV_ENTITY,
    CONF_SURPLUS_THRESHOLD_W,
    DEFAULT_AZIMUTH,
    DEFAULT_BATTERY_CAPACITY_KWH,
    DEFAULT_BATTERY_SIGN,
    DEFAULT_DECLINATION,
    DEFAULT_FORECAST_POLL_MINUTES,
    DEFAULT_GRID_SIGN,
    DEFAULT_KWP,
    DEFAULT_MIN_RESERVE_PERCENT,
    DEFAULT_NIGHT_CONSUMPTION_KWH,
    DEFAULT_SURPLUS_THRESHOLD_W,
    DOMAIN,
    GRID_SIGN_OPTIONS,
    MAX_FORECAST_POLL_MINUTES,
    MIN_FORECAST_POLL_MINUTES,
    NAME,
    POWER_UNIT_FACTORS,
)

POWER_ENTITY_FIELDS = (
    CONF_PV_ENTITY,
    CONF_GRID_ENTITY,
    CONF_BATTERY_POWER_ENTITY,
)

# key -> (minimum, maximum)
_NUMERIC_RANGES: dict[str, tuple[float, float]] = {
    CONF_LATITUDE: (-90.0, 90.0),
    CONF_LONGITUDE: (-180.0, 180.0),
    CONF_DECLINATION: (0.0, 90.0),
    CONF_AZIMUTH: (-180.0, 180.0),
    CONF_KWP: (0.01, 100_000.0),
    CONF_BATTERY_CAPACITY_KWH: (0.01, 100_000.0),
    CONF_MIN_RESERVE_PERCENT: (0.0, 100.0),
    CONF_NIGHT_CONSUMPTION_KWH: (0.0, 100_000.0),
    CONF_SURPLUS_THRESHOLD_W: (0.0, 1_000_000.0),
    CONF_FORECAST_POLL_MINUTES: (
        float(MIN_FORECAST_POLL_MINUTES),
        float(MAX_FORECAST_POLL_MINUTES),
    ),
}

_INTEGER_FIELDS = (
    CONF_DECLINATION,
    CONF_AZIMUTH,
    CONF_SURPLUS_THRESHOLD_W,
    CONF_FORECAST_POLL_MINUTES,
)

_FLOAT_FIELDS = (
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_KWP,
    CONF_BATTERY_CAPACITY_KWH,
    CONF_MIN_RESERVE_PERCENT,
    CONF_NIGHT_CONSUMPTION_KWH,
)


def _initial_values(hass: HomeAssistant) -> dict[str, Any]:
    """Return the defaults used by a brand new config entry."""
    return {
        CONF_LATITUDE: hass.config.latitude,
        CONF_LONGITUDE: hass.config.longitude,
        CONF_DECLINATION: DEFAULT_DECLINATION,
        CONF_AZIMUTH: DEFAULT_AZIMUTH,
        CONF_KWP: DEFAULT_KWP,
        CONF_GRID_SIGN: DEFAULT_GRID_SIGN,
        CONF_BATTERY_SIGN: DEFAULT_BATTERY_SIGN,
        CONF_BATTERY_CAPACITY_KWH: DEFAULT_BATTERY_CAPACITY_KWH,
        CONF_MIN_RESERVE_PERCENT: DEFAULT_MIN_RESERVE_PERCENT,
        CONF_NIGHT_CONSUMPTION_KWH: DEFAULT_NIGHT_CONSUMPTION_KWH,
        CONF_SURPLUS_THRESHOLD_W: DEFAULT_SURPLUS_THRESHOLD_W,
        CONF_FORECAST_POLL_MINUTES: DEFAULT_FORECAST_POLL_MINUTES,
    }


def _entry_values(entry: ConfigEntry) -> dict[str, Any]:
    """Return the current entry data merged with its options."""
    return {**entry.data, **entry.options}


def _number_selector(
    minimum: float, maximum: float, step: int | None, unit: str
) -> selector.NumberSelector:
    """Build a numeric selector in box mode.

    Home Assistant requires ``step`` to be an integer, so fractional fields
    (lat/lon, kWp, kWh) omit it entirely and accept any typed value.
    """
    config: dict[str, Any] = {
        "min": minimum,
        "max": maximum,
        "unit_of_measurement": unit,
        "mode": selector.NumberSelectorMode.BOX,
    }
    if step is not None:
        config["step"] = int(step)
    return selector.NumberSelector(selector.NumberSelectorConfig(**config))


def _number_marker(key: str, values: Mapping[str, Any], default: float) -> vol.Marker:
    """Return a required numeric field marker, keeping the current value."""
    return vol.Required(key, default=values.get(key, default))


def _required_field(key: str, values: Mapping[str, Any]) -> vol.Marker:
    """Return a required marker, keeping the current value as fallback."""
    current = values.get(key)
    if current is None:
        return vol.Required(key)
    return vol.Required(key, default=current)


def _power_selector() -> selector.EntitySelector:
    """Build the selector used for power sensors."""
    return selector.EntitySelector(
        selector.EntitySelectorConfig(
            domain="sensor",
            device_class=SensorDeviceClass.POWER,
        )
    )


def _sign_selector(
    translation_key: str, options: tuple[str, ...]
) -> selector.SelectSelector:
    """Build a translated dropdown selector."""
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=list(options),
            translation_key=translation_key,
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )


def _build_schema(
    values: Mapping[str, Any], *, include_poll_interval: bool = False
) -> vol.Schema:
    """Build the shared config/options schema.

    Config and options expose exactly the same fields, so both flows use this
    helper. The options flow merely adds the poll interval.
    """
    fields: dict[Any, Any] = {}

    def add_number(
        key: str,
        default: float,
        minimum: float,
        maximum: float,
        step: float,
        unit: str,
    ) -> None:
        fields[_number_marker(key, values, default)] = _number_selector(
            minimum, maximum, step, unit
        )

    add_number(CONF_LATITUDE, 0.0, -90.0, 90.0, None, "°")
    add_number(CONF_LONGITUDE, 0.0, -180.0, 180.0, None, "°")
    add_number(CONF_DECLINATION, DEFAULT_DECLINATION, 0.0, 90.0, 1, "°")
    add_number(CONF_AZIMUTH, DEFAULT_AZIMUTH, -180.0, 180.0, 1, "°")
    add_number(CONF_KWP, DEFAULT_KWP, 0.01, 100_000.0, None, "kWp")

    fields[_required_field(CONF_PV_ENTITY, values)] = _power_selector()
    fields[_required_field(CONF_GRID_ENTITY, values)] = _power_selector()
    fields[
        vol.Required(
            CONF_GRID_SIGN, default=values.get(CONF_GRID_SIGN, DEFAULT_GRID_SIGN)
        )
    ] = _sign_selector("grid_sign", GRID_SIGN_OPTIONS)

    fields[_required_field(CONF_BATTERY_POWER_ENTITY, values)] = _power_selector()
    fields[
        vol.Required(
            CONF_BATTERY_SIGN,
            default=values.get(CONF_BATTERY_SIGN, DEFAULT_BATTERY_SIGN),
        )
    ] = _sign_selector("battery_sign", BATTERY_SIGN_OPTIONS)

    fields[_required_field(CONF_BATTERY_SOC_ENTITY, values)] = selector.EntitySelector(
        selector.EntitySelectorConfig(domain="sensor")
    )

    add_number(
        CONF_BATTERY_CAPACITY_KWH,
        DEFAULT_BATTERY_CAPACITY_KWH,
        0.01,
        100_000.0,
        None,
        "kWh",
    )
    add_number(
        CONF_MIN_RESERVE_PERCENT,
        DEFAULT_MIN_RESERVE_PERCENT,
        0.0,
        100.0,
        1,
        "%",
    )
    add_number(
        CONF_NIGHT_CONSUMPTION_KWH,
        DEFAULT_NIGHT_CONSUMPTION_KWH,
        0.0,
        100_000.0,
        None,
        "kWh",
    )
    add_number(
        CONF_SURPLUS_THRESHOLD_W,
        DEFAULT_SURPLUS_THRESHOLD_W,
        0.0,
        1_000_000.0,
        10,
        "W",
    )

    if include_poll_interval:
        add_number(
            CONF_FORECAST_POLL_MINUTES,
            DEFAULT_FORECAST_POLL_MINUTES,
            float(MIN_FORECAST_POLL_MINUTES),
            float(MAX_FORECAST_POLL_MINUTES),
            1,
            "min",
        )

    return vol.Schema(fields)


def _is_power_sensor(hass: HomeAssistant, entity_id: Any) -> bool:
    """Return True when the entity looks like a power sensor."""
    if not isinstance(entity_id, str) or not entity_id.startswith("sensor."):
        return False
    state = hass.states.get(entity_id)
    if state is None:
        return False
    unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
    if unit is None:
        # A unitless template sensor is assumed to be in W.
        return True
    return str(unit).strip().lower() in POWER_UNIT_FACTORS


def _is_percentage_sensor(hass: HomeAssistant, entity_id: Any) -> bool:
    """Return True when the entity reports a percentage."""
    if not isinstance(entity_id, str) or not entity_id.startswith("sensor."):
        return False
    state = hass.states.get(entity_id)
    if state is None:
        return False
    unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
    if unit is None:
        return True
    return str(unit).strip() == "%"


def _to_float(value: Any) -> float | None:
    """Return *value* as float, or None."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _validate_input(
    hass: HomeAssistant, user_input: Mapping[str, Any]
) -> dict[str, str]:
    """Validate entity types, units and numeric ranges.

    Errors are keyed by field so the frontend can highlight the offending
    input.
    """
    errors: dict[str, str] = {}

    for key in POWER_ENTITY_FIELDS:
        if not _is_power_sensor(hass, user_input.get(key)):
            errors[key] = "invalid_entity"

    if not _is_percentage_sensor(hass, user_input.get(CONF_BATTERY_SOC_ENTITY)):
        errors[CONF_BATTERY_SOC_ENTITY] = "invalid_entity"

    for key, (minimum, maximum) in _NUMERIC_RANGES.items():
        if key not in user_input:
            continue
        value = _to_float(user_input[key])
        if value is None or not minimum <= value <= maximum:
            errors[key] = "invalid_value"

    if user_input.get(CONF_GRID_SIGN) not in GRID_SIGN_OPTIONS:
        errors[CONF_GRID_SIGN] = "invalid_value"
    if user_input.get(CONF_BATTERY_SIGN) not in BATTERY_SIGN_OPTIONS:
        errors[CONF_BATTERY_SIGN] = "invalid_value"

    return errors


def _normalise(user_input: Mapping[str, Any]) -> dict[str, Any]:
    """Convert form values to the types used by the integration."""
    data = dict(user_input)
    for key in _INTEGER_FIELDS:
        if (value := _to_float(data.get(key))) is not None:
            data[key] = round(value)
    for key in _FLOAT_FIELDS:
        if (value := _to_float(data.get(key))) is not None:
            data[key] = round(value, 4)
    return data


class PvPlannerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial setup of PV Planner."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the Forecast.Solar site and the source entities."""
        errors: dict[str, str] = {}

        if user_input is not None:
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()
            errors = _validate_input(self.hass, user_input)
            if not errors:
                return self.async_create_entry(title=NAME, data=_normalise(user_input))

        values = _initial_values(self.hass)
        if user_input is not None:
            values.update(user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=_build_schema(values),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> PvPlannerOptionsFlow:
        """Return the options flow for this config entry."""
        return PvPlannerOptionsFlow()


class PvPlannerOptionsFlow(OptionsFlowWithReload):
    """Edit every PV Planner setting; the entry reloads when saved."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the same fields as the config flow plus the poll interval."""
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = _validate_input(self.hass, user_input)
            if not errors:
                return self.async_create_entry(title="", data=_normalise(user_input))

        values = {**_initial_values(self.hass), **_entry_values(self.config_entry)}
        if user_input is not None:
            values.update(user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=_build_schema(values, include_poll_interval=True),
            errors=errors,
        )
