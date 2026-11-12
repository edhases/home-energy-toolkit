"""Data coordinator for the Energy Cost integration."""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass
from datetime import date, datetime
from datetime import time as dt_time
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import (
    Event,
    EventStateChangedData,
    HomeAssistant,
    callback,
)
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

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
    DOMAIN,
    ENERGY_UNIT_FACTORS,
    SAVE_INTERVAL,
    STORAGE_VERSION,
    TARIFF_DAY,
    TARIFF_MODE_SINGLE,
    TARIFF_NIGHT,
    TOTAL_KEYS,
    UPDATE_INTERVAL,
)
from .tariff import active_tariff, billing_period_start, month_key, parse_clock

_LOGGER = logging.getLogger(__name__)

_ENERGY_ENTITY_KEYS = (
    CONF_IMPORT_ENERGY_ENTITY,
    CONF_EXPORT_ENERGY_ENTITY,
    CONF_PV_ENERGY_ENTITY,
)


@dataclass(frozen=True, slots=True)
class EnergyCostData:
    """Calculated values exposed to the sensor platform."""

    period_start: date
    import_cost_period: float
    export_revenue_period: float
    pv_saved_period: float
    cost_period: float
    cost_today: float
    cost_month: float
    cost_total: float
    import_cost_total: float
    export_revenue_total: float
    pv_saved_total: float
    current_price: float
    tariff_now: str
    currency: str
    tariff_mode: str
    last_update: datetime


def _as_float(value: Any, default: float = 0.0) -> float:
    """Coerce a stored value to a finite float."""
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def _as_optional_float(value: Any) -> float | None:
    """Coerce a stored value to a finite float or None."""
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _parse_date(value: Any) -> date | None:
    """Parse an ISO date from storage."""
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


class EnergyCostCoordinator(DataUpdateCoordinator[EnergyCostData]):
    """Calculate energy costs from cumulative kWh sensors."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.entry = entry
        self.config: dict[str, Any] = {**DEFAULT_CONFIG, **entry.data, **entry.options}
        self._currency = str(self.config.get(CONF_CURRENCY) or DEFAULT_CURRENCY)
        self._tariff_mode = str(self.config.get(CONF_TARIFF_MODE) or TARIFF_MODE_SINGLE)
        self._night_start = parse_clock(
            self.config.get(CONF_NIGHT_START), dt_time(23, 0)
        )
        self._night_end = parse_clock(self.config.get(CONF_NIGHT_END), dt_time(7, 0))
        self._month_start_day = int(
            _as_float(self.config.get(CONF_MONTH_START_DAY), 1)
        )
        self._month_start_day = max(1, min(28, self._month_start_day))

        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )
        self._unsub_state: Any = None
        self._last_save = 0.0

        today = dt_util.now().date()
        self._period_start = billing_period_start(today, self._month_start_day)
        self._today = today
        self._month_key = month_key(today)

        self._import_base: float | None = None
        self._export_base: float | None = None
        self._pv_base: float | None = None
        self._last_import: float | None = None
        self._last_export: float | None = None
        self._last_pv: float | None = None

        self._import_cost_period = 0.0
        self._export_revenue_period = 0.0
        self._pv_saved_period = 0.0
        self._cost_today = 0.0
        self._cost_month = 0.0
        self._totals: dict[str, float] = {key: 0.0 for key in TOTAL_KEYS}

        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )

    @property
    def currency(self) -> str:
        """Return the configured currency symbol."""
        return self._currency

    @property
    def tracked_entities(self) -> list[str]:
        """Return the configured energy entity IDs."""
        entities: list[str] = []
        for key in _ENERGY_ENTITY_KEYS:
            entity_id = self.config.get(key)
            if isinstance(entity_id, str) and entity_id:
                entities.append(entity_id)
        return entities

    async def async_setup(self) -> None:
        """Restore persisted accumulators."""
        await self._async_restore()

    @callback
    def async_start_listening(self) -> None:
        """Subscribe to state changes of the configured energy sensors."""
        if self._unsub_state is not None:
            return
        entities = self.tracked_entities
        if entities:
            self._unsub_state = async_track_state_change_event(
                self.hass, entities, self._handle_state_change
            )

    async def async_shutdown(self) -> None:
        """Persist the final state and stop listening for changes."""
        if self._unsub_state is not None:
            self._unsub_state()
            self._unsub_state = None
        await self._async_save(force=True)
        await super().async_shutdown()

    @callback
    def _handle_state_change(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Recalculate when a tracked energy sensor changes."""
        self.hass.async_create_task(self.async_request_refresh())

    async def _async_restore(self) -> None:
        """Load the persisted accumulators."""
        stored = await self._store.async_load()
        if not isinstance(stored, dict):
            _LOGGER.debug("No stored state for %s, starting fresh", self.entry.entry_id)
            return

        self._import_base = _as_optional_float(stored.get("import_base"))
        self._export_base = _as_optional_float(stored.get("export_base"))
        self._pv_base = _as_optional_float(stored.get("pv_base"))
        self._last_import = _as_optional_float(stored.get("last_import"))
        self._last_export = _as_optional_float(stored.get("last_export"))
        self._last_pv = _as_optional_float(stored.get("last_pv"))

        # Re-base when a monitored entity was replaced to avoid pricing the
        # difference between two unrelated meters.
        if stored.get("import_entity") != self.config.get(CONF_IMPORT_ENERGY_ENTITY):
            self._import_base = None
            self._last_import = None
        if stored.get("export_entity") != self.config.get(CONF_EXPORT_ENERGY_ENTITY):
            self._export_base = None
            self._last_export = None
        if stored.get("pv_entity") != self.config.get(CONF_PV_ENERGY_ENTITY):
            self._pv_base = None
            self._last_pv = None

        self._import_cost_period = _as_float(stored.get("import_cost_period"))
        self._export_revenue_period = _as_float(
            stored.get("export_revenue_period")
        )
        self._pv_saved_period = _as_float(stored.get("pv_saved_period"))
        self._cost_today = _as_float(stored.get("cost_today"))
        self._cost_month = _as_float(stored.get("cost_month"))

        totals = stored.get("totals")
        if isinstance(totals, dict):
            self._totals = {key: _as_float(totals.get(key)) for key in TOTAL_KEYS}

        today = dt_util.now().date()
        self._period_start = (
            _parse_date(stored.get("period_start"))
            or billing_period_start(today, self._month_start_day)
        )
        self._today = _parse_date(stored.get("today_date")) or today
        stored_month = stored.get("month_key")
        self._month_key = (
            stored_month if isinstance(stored_month, str) else month_key(today)
        )

    def _roll_over(self, today: date) -> None:
        """Reset accumulators when a billing period, day or month starts."""
        period_start = billing_period_start(today, self._month_start_day)
        if self._period_start != period_start:
            _LOGGER.debug(
                "Billing period rolled over from %s to %s",
                self._period_start,
                period_start,
            )
            self._period_start = period_start
            self._import_cost_period = 0.0
            self._export_revenue_period = 0.0
            self._pv_saved_period = 0.0
            self._import_base = self._last_import
            self._export_base = self._last_export
            self._pv_base = self._last_pv

        if self._today != today:
            self._today = today
            self._cost_today = 0.0

        current_month = month_key(today)
        if self._month_key != current_month:
            self._month_key = current_month
            self._cost_month = 0.0

    def _read_kwh(self, entity_id: str | None) -> float | None:
        """Read an energy sensor and normalize it to kWh."""
        if not entity_id:
            return None

        state = self.hass.states.get(entity_id)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None

        try:
            value = float(state.state)
        except (TypeError, ValueError):
            return None

        if not math.isfinite(value):
            return None

        unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
        factor = ENERGY_UNIT_FACTORS.get(str(unit).strip()) if unit else None
        if factor is None:
            _LOGGER.debug(
                "Skipping %s: unsupported unit %s", entity_id, unit
            )
            return None

        return value * factor

    @staticmethod
    def _delta(current: float | None, previous: float | None) -> tuple[float, float | None]:
        """Return a non-negative delta and the new baseline."""
        if current is None:
            return 0.0, previous
        if previous is None:
            return 0.0, current
        if current < previous:
            # Counter reset or replacement: rebase without pricing the drop.
            return 0.0, current
        return current - previous, current

    def _price_for(self, tariff: str) -> float:
        """Return the import price for a tariff state."""
        if tariff == TARIFF_NIGHT:
            return _as_float(self.config.get(CONF_PRICE_NIGHT))
        if tariff == TARIFF_DAY:
            return _as_float(self.config.get(CONF_PRICE_DAY))
        return _as_float(self.config.get(CONF_PRICE_SINGLE))

    async def _async_update_data(self) -> EnergyCostData:
        """Read the sensors, price the deltas and roll periods over."""
        now = dt_util.now()
        today = now.date()
        self._roll_over(today)

        import_kwh = self._read_kwh(self.config.get(CONF_IMPORT_ENERGY_ENTITY))
        export_kwh = self._read_kwh(self.config.get(CONF_EXPORT_ENERGY_ENTITY))
        pv_kwh = self._read_kwh(self.config.get(CONF_PV_ENERGY_ENTITY))

        if self._import_base is None and import_kwh is not None:
            self._import_base = import_kwh
        if self._export_base is None and export_kwh is not None:
            self._export_base = export_kwh
        if self._pv_base is None and pv_kwh is not None:
            self._pv_base = pv_kwh

        import_delta, self._last_import = self._delta(import_kwh, self._last_import)
        export_delta, self._last_export = self._delta(export_kwh, self._last_export)
        pv_delta, self._last_pv = self._delta(pv_kwh, self._last_pv)

        tariff = active_tariff(
            self._tariff_mode, self._night_start, self._night_end, now.time()
        )
        import_price = self._price_for(tariff)
        export_price = _as_float(self.config.get(CONF_EXPORT_PRICE))

        import_cost = import_delta * import_price
        export_revenue = export_delta * export_price
        pv_saved = pv_delta * import_price

        self._import_cost_period += import_cost
        self._export_revenue_period += export_revenue
        self._pv_saved_period += pv_saved

        net_cost = import_cost - export_revenue
        self._cost_today += net_cost
        self._cost_month += net_cost

        self._totals["import_cost"] += import_cost
        self._totals["export_revenue"] += export_revenue
        self._totals["pv_saved"] += pv_saved
        self._totals["cost"] = (
            self._totals["import_cost"] - self._totals["export_revenue"]
        )

        await self._async_save()

        return EnergyCostData(
            period_start=self._period_start,
            import_cost_period=self._import_cost_period,
            export_revenue_period=self._export_revenue_period,
            pv_saved_period=self._pv_saved_period,
            cost_period=self._import_cost_period - self._export_revenue_period,
            cost_today=self._cost_today,
            cost_month=self._cost_month,
            cost_total=self._totals["cost"],
            import_cost_total=self._totals["import_cost"],
            export_revenue_total=self._totals["export_revenue"],
            pv_saved_total=self._totals["pv_saved"],
            current_price=import_price,
            tariff_now=tariff,
            currency=self._currency,
            tariff_mode=self._tariff_mode,
            last_update=now,
        )

    def _as_storage_dict(self) -> dict[str, Any]:
        """Serialize the accumulators for persistence."""
        return {
            "period_start": self._period_start.isoformat(),
            "import_base": self._import_base,
            "export_base": self._export_base,
            "pv_base": self._pv_base,
            "cost_period": self._import_cost_period - self._export_revenue_period,
            "import_cost_period": self._import_cost_period,
            "export_revenue_period": self._export_revenue_period,
            "pv_saved_period": self._pv_saved_period,
            "last_import": self._last_import,
            "last_export": self._last_export,
            "last_pv": self._last_pv,
            "import_entity": self.config.get(CONF_IMPORT_ENERGY_ENTITY),
            "export_entity": self.config.get(CONF_EXPORT_ENERGY_ENTITY),
            "pv_entity": self.config.get(CONF_PV_ENERGY_ENTITY),
            "totals": dict(self._totals),
            "cost_today": self._cost_today,
            "today_date": self._today.isoformat(),
            "cost_month": self._cost_month,
            "month_key": self._month_key,
        }

    async def _async_save(self, *, force: bool = False) -> None:
        """Persist at most once per SAVE_INTERVAL seconds."""
        now = time.monotonic()
        if not force and self._last_save and now - self._last_save < SAVE_INTERVAL:
            return
        self._last_save = now
        await self._store.async_save(self._as_storage_dict())
