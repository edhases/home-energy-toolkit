"""Constants for the Energy Cost integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "energy_cost"
MANUFACTURER: Final = "Home Energy Toolkit"
MODEL: Final = "Energy Cost"

PLATFORMS: Final[list[Platform]] = [Platform.SENSOR]

CONF_IMPORT_ENERGY_ENTITY: Final = "import_energy_entity"
CONF_EXPORT_ENERGY_ENTITY: Final = "export_energy_entity"
CONF_PV_ENERGY_ENTITY: Final = "pv_energy_entity"
CONF_TARIFF_MODE: Final = "tariff_mode"
CONF_PRICE_SINGLE: Final = "price_single"
CONF_PRICE_DAY: Final = "price_day"
CONF_PRICE_NIGHT: Final = "price_night"
CONF_NIGHT_START: Final = "night_start"
CONF_NIGHT_END: Final = "night_end"
CONF_EXPORT_PRICE: Final = "export_price"
CONF_CURRENCY: Final = "currency"
CONF_MONTH_START_DAY: Final = "month_start_day"

TARIFF_MODE_SINGLE: Final = "single"
TARIFF_MODE_DUAL: Final = "dual"
TARIFF_DAY: Final = "day"
TARIFF_NIGHT: Final = "night"

TARIFF_MODES: Final[list[str]] = [TARIFF_MODE_SINGLE, TARIFF_MODE_DUAL]
TARIFF_STATES: Final[list[str]] = [TARIFF_DAY, TARIFF_NIGHT, TARIFF_MODE_SINGLE]

DEFAULT_TARIFF_MODE: Final = TARIFF_MODE_SINGLE
DEFAULT_PRICE_SINGLE: Final = 4.32
DEFAULT_PRICE_DAY: Final = 4.32
DEFAULT_PRICE_NIGHT: Final = 2.16
DEFAULT_NIGHT_START: Final = "23:00"
DEFAULT_NIGHT_END: Final = "07:00"
DEFAULT_EXPORT_PRICE: Final = 0.0
DEFAULT_CURRENCY: Final = "₴"
DEFAULT_MONTH_START_DAY: Final = 1

# Energy sensors are normalized to kWh before deltas are calculated.
ENERGY_UNIT_FACTORS: Final[dict[str, float]] = {
    "kWh": 1.0,
    "Wh": 0.001,
    "MWh": 1000.0,
}

UPDATE_INTERVAL: Final = timedelta(seconds=60)
SAVE_INTERVAL: Final = 60.0

STORAGE_VERSION: Final = 1

TOTAL_KEYS: Final[tuple[str, ...]] = (
    "cost",
    "import_cost",
    "export_revenue",
    "pv_saved",
)

DEFAULT_CONFIG: Final[dict[str, object]] = {
    CONF_TARIFF_MODE: DEFAULT_TARIFF_MODE,
    CONF_PRICE_SINGLE: DEFAULT_PRICE_SINGLE,
    CONF_PRICE_DAY: DEFAULT_PRICE_DAY,
    CONF_PRICE_NIGHT: DEFAULT_PRICE_NIGHT,
    CONF_NIGHT_START: DEFAULT_NIGHT_START,
    CONF_NIGHT_END: DEFAULT_NIGHT_END,
    CONF_EXPORT_PRICE: DEFAULT_EXPORT_PRICE,
    CONF_CURRENCY: DEFAULT_CURRENCY,
    CONF_MONTH_START_DAY: DEFAULT_MONTH_START_DAY,
}
