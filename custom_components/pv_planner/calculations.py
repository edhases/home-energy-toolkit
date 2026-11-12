"""Derived power and energy calculations for PV Planner.

Everything in this module is pure: sensor states are read from the state
machine, the configured sign conventions are applied, and a single
:class:`PlannerSnapshot` is produced. Keeping the maths in one place means
the sensor and binary_sensor platforms can never disagree with each other.

Formulas (all powers are normalised to W first):

    grid_power > 0 and positive_is_import -> import = grid,  export = 0
    grid_power < 0 and negative_is_import -> import = -grid, export = 0

    home_load = pv_now + battery_discharge + import - battery_charge - export
    home_load = max(home_load, 0)

    power_surplus = pv_now - home_load - battery_charge

``power_surplus`` therefore also equals
``export - import - battery_charge - battery_discharge``: it is the power
that could be sent to an *additional* load right now without importing,
discharging the battery, or reducing an existing battery charge.

The reserve check compares the energy currently stored in the battery with

    night_consumption_kwh + min_reserve_percent / 100 * capacity_kwh
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant, State

from .const import (
    ADVICE_HOLD,
    ADVICE_NO_DATA,
    ADVICE_RESERVE_LOW,
    ADVICE_SURPLUS,
    BATTERY_SIGN_POSITIVE_CHARGING,
    CONF_BATTERY_CAPACITY_KWH,
    CONF_BATTERY_POWER_ENTITY,
    CONF_BATTERY_SIGN,
    CONF_BATTERY_SOC_ENTITY,
    CONF_GRID_ENTITY,
    CONF_GRID_SIGN,
    CONF_MIN_RESERVE_PERCENT,
    CONF_NIGHT_CONSUMPTION_KWH,
    CONF_PV_ENTITY,
    CONF_SURPLUS_THRESHOLD_W,
    DEFAULT_BATTERY_CAPACITY_KWH,
    DEFAULT_MIN_RESERVE_PERCENT,
    DEFAULT_NIGHT_CONSUMPTION_KWH,
    DEFAULT_SURPLUS_THRESHOLD_W,
    GRID_SIGN_POSITIVE_IMPORT,
    POWER_UNIT_FACTORS,
)

_UNAVAILABLE_STATES = (STATE_UNKNOWN, STATE_UNAVAILABLE)


def as_float(value: Any) -> float | None:
    """Return *value* as float, or None when it is not numeric."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _read_state(hass: HomeAssistant, entity_id: Any) -> State | None:
    """Return a usable state object for *entity_id*, else None."""
    if not isinstance(entity_id, str) or not entity_id:
        return None
    state = hass.states.get(entity_id)
    if state is None or state.state in _UNAVAILABLE_STATES:
        return None
    return state


def read_power(hass: HomeAssistant, entity_id: Any) -> float | None:
    """Read a power sensor and convert its value to W.

    A missing unit is treated as W (a very common convention for template
    sensors). Any other unknown unit makes the reading unusable.
    """
    state = _read_state(hass, entity_id)
    if state is None:
        return None
    value = as_float(state.state)
    if value is None:
        return None
    unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
    if unit is None:
        return value
    factor = POWER_UNIT_FACTORS.get(str(unit).strip().lower())
    if factor is None:
        return None
    return value * factor


def read_percentage(hass: HomeAssistant, entity_id: Any) -> float | None:
    """Read a state-of-charge sensor in percent."""
    state = _read_state(hass, entity_id)
    if state is None:
        return None
    value = as_float(state.state)
    if value is None:
        return None
    unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
    if unit is not None and str(unit).strip() != "%":
        return None
    return value


def _config_float(config: Mapping[str, Any], key: str, default: float) -> float:
    """Return a numeric option, falling back to *default*."""
    value = as_float(config.get(key))
    return default if value is None else value


@dataclass(frozen=True, slots=True)
class PlannerSnapshot:
    """All derived values for one point in time."""

    pv_now_w: float | None = None
    grid_w: float | None = None
    battery_w: float | None = None
    soc_percent: float | None = None
    import_w: float | None = None
    export_w: float | None = None
    battery_charge_w: float | None = None
    battery_discharge_w: float | None = None
    home_load_w: float | None = None
    surplus_w: float | None = None
    battery_remaining_kwh: float | None = None
    battery_reserve_needed_kwh: float = 0.0
    reserve_ok: bool | None = None
    advice: str = ADVICE_NO_DATA


def build_snapshot(hass: HomeAssistant, config: Mapping[str, Any]) -> PlannerSnapshot:
    """Read the configured entities and derive every PV Planner value."""
    pv_now = read_power(hass, config.get(CONF_PV_ENTITY))
    grid = read_power(hass, config.get(CONF_GRID_ENTITY))
    battery = read_power(hass, config.get(CONF_BATTERY_POWER_ENTITY))
    soc = read_percentage(hass, config.get(CONF_BATTERY_SOC_ENTITY))

    # Split the signed grid reading into import/export.
    import_w: float | None = None
    export_w: float | None = None
    if grid is not None:
        if config.get(CONF_GRID_SIGN) == GRID_SIGN_POSITIVE_IMPORT:
            import_w = max(grid, 0.0)
            export_w = max(-grid, 0.0)
        else:
            import_w = max(-grid, 0.0)
            export_w = max(grid, 0.0)

    # Split the signed battery reading into charge/discharge.
    battery_charge: float | None = None
    battery_discharge: float | None = None
    if battery is not None:
        if config.get(CONF_BATTERY_SIGN) == BATTERY_SIGN_POSITIVE_CHARGING:
            battery_charge = max(battery, 0.0)
            battery_discharge = max(-battery, 0.0)
        else:
            battery_charge = max(-battery, 0.0)
            battery_discharge = max(battery, 0.0)

    home_load: float | None = None
    if (
        pv_now is not None
        and import_w is not None
        and export_w is not None
        and battery_charge is not None
        and battery_discharge is not None
    ):
        home_load = max(
            0.0,
            pv_now + battery_discharge + import_w - battery_charge - export_w,
        )

    surplus: float | None = None
    if pv_now is not None and home_load is not None and battery_charge is not None:
        surplus = pv_now - home_load - battery_charge

    capacity = _config_float(
        config, CONF_BATTERY_CAPACITY_KWH, DEFAULT_BATTERY_CAPACITY_KWH
    )
    night_consumption = _config_float(
        config, CONF_NIGHT_CONSUMPTION_KWH, DEFAULT_NIGHT_CONSUMPTION_KWH
    )
    reserve_percent = _config_float(
        config, CONF_MIN_RESERVE_PERCENT, DEFAULT_MIN_RESERVE_PERCENT
    )

    remaining = None if soc is None else soc / 100.0 * capacity
    reserve_floor = night_consumption + reserve_percent / 100.0 * capacity
    reserve_ok = None if remaining is None else remaining >= reserve_floor

    threshold = _config_float(
        config, CONF_SURPLUS_THRESHOLD_W, DEFAULT_SURPLUS_THRESHOLD_W
    )

    # "no_data" wins over everything else: without all key entities we cannot
    # make an honest recommendation.
    if (
        pv_now is None
        or grid is None
        or battery is None
        or soc is None
        or reserve_ok is None
    ):
        advice = ADVICE_NO_DATA
    elif not reserve_ok:
        advice = ADVICE_RESERVE_LOW
    elif surplus is not None and surplus >= threshold:
        advice = ADVICE_SURPLUS
    else:
        advice = ADVICE_HOLD

    return PlannerSnapshot(
        pv_now_w=pv_now,
        grid_w=grid,
        battery_w=battery,
        soc_percent=soc,
        import_w=import_w,
        export_w=export_w,
        battery_charge_w=battery_charge,
        battery_discharge_w=battery_discharge,
        home_load_w=home_load,
        surplus_w=surplus,
        battery_remaining_kwh=remaining,
        battery_reserve_needed_kwh=night_consumption,
        reserve_ok=reserve_ok,
        advice=advice,
    )
