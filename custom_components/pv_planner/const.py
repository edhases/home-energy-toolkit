"""Constants for the PV Planner integration.

PV Planner is a read-only decision helper. It never switches devices itself:
it only exposes sensors that the user can act on from automations.
"""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "pv_planner"
NAME: Final = "PV Planner"
VERSION: Final = "0.1.0"
DOCUMENTATION_URL: Final = "https://github.com/edhases/home-energy-toolkit"

# --------------------------------------------------------------------------
# Configuration keys
# --------------------------------------------------------------------------
CONF_DECLINATION: Final = "declination"
CONF_AZIMUTH: Final = "azimuth"
CONF_KWP: Final = "kwp"
CONF_PV_ENTITY: Final = "pv_entity"
CONF_GRID_ENTITY: Final = "grid_entity"
CONF_GRID_SIGN: Final = "grid_sign"
CONF_BATTERY_POWER_ENTITY: Final = "battery_power_entity"
CONF_BATTERY_SIGN: Final = "battery_sign"
CONF_BATTERY_SOC_ENTITY: Final = "battery_soc_entity"
CONF_BATTERY_CAPACITY_KWH: Final = "battery_capacity_kwh"
CONF_MIN_RESERVE_PERCENT: Final = "min_reserve_percent"
CONF_NIGHT_CONSUMPTION_KWH: Final = "night_consumption_kwh"
CONF_SURPLUS_THRESHOLD_W: Final = "surplus_threshold_w"
CONF_FORECAST_POLL_MINUTES: Final = "forecast_poll_minutes"

# --------------------------------------------------------------------------
# Sign conventions
# --------------------------------------------------------------------------
GRID_SIGN_NEGATIVE_IMPORT: Final = "negative_is_import"
GRID_SIGN_POSITIVE_IMPORT: Final = "positive_is_import"
GRID_SIGN_OPTIONS: Final = (
    GRID_SIGN_NEGATIVE_IMPORT,
    GRID_SIGN_POSITIVE_IMPORT,
)

BATTERY_SIGN_POSITIVE_CHARGING: Final = "positive_is_charging"
BATTERY_SIGN_NEGATIVE_CHARGING: Final = "negative_is_charging"
BATTERY_SIGN_OPTIONS: Final = (
    BATTERY_SIGN_POSITIVE_CHARGING,
    BATTERY_SIGN_NEGATIVE_CHARGING,
)

# --------------------------------------------------------------------------
# Defaults
# --------------------------------------------------------------------------
DEFAULT_DECLINATION: Final = 35
DEFAULT_AZIMUTH: Final = 0
DEFAULT_KWP: Final = 5.0
DEFAULT_GRID_SIGN: Final = GRID_SIGN_NEGATIVE_IMPORT
DEFAULT_BATTERY_SIGN: Final = BATTERY_SIGN_POSITIVE_CHARGING
DEFAULT_BATTERY_CAPACITY_KWH: Final = 5.0
DEFAULT_MIN_RESERVE_PERCENT: Final = 20.0
DEFAULT_NIGHT_CONSUMPTION_KWH: Final = 2.0
DEFAULT_SURPLUS_THRESHOLD_W: Final = 200
DEFAULT_FORECAST_POLL_MINUTES: Final = 60

# Forecast.Solar allows 12 requests per hour on the free tier. Polling more
# often than once per hour would burn through that budget and get us blocked.
MIN_FORECAST_POLL_MINUTES: Final = 60
MAX_FORECAST_POLL_MINUTES: Final = 1440

# --------------------------------------------------------------------------
# Forecast.Solar
# --------------------------------------------------------------------------
FORECAST_SOLAR_URL: Final = (
    "https://api.forecast.solar/estimate/"
    "{latitude}/{longitude}/{declination}/{azimuth}/{kwp}"
)
PROVIDER_FORECAST_SOLAR: Final = "forecast_solar"
FORECAST_SOLAR_TIMEOUT: Final = 30

# --------------------------------------------------------------------------
# Energy advice states
# --------------------------------------------------------------------------
ADVICE_SURPLUS: Final = "surplus"
ADVICE_HOLD: Final = "hold"
ADVICE_RESERVE_LOW: Final = "reserve_low"
ADVICE_NO_DATA: Final = "no_data"
ADVICE_OPTIONS: Final = (
    ADVICE_SURPLUS,
    ADVICE_HOLD,
    ADVICE_RESERVE_LOW,
    ADVICE_NO_DATA,
)

# --------------------------------------------------------------------------
# Unit handling
# --------------------------------------------------------------------------
# Sensor states are normalised to W / W before any arithmetic happens.
POWER_UNIT_FACTORS: Final[dict[str, float]] = {
    "w": 1.0,
    "kw": 1_000.0,
    "mw": 1_000_000.0,
}
