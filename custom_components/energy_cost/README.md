# Energy Cost

A Home Assistant custom integration that turns cumulative energy sensors (kWh) into money: grid import cost, export revenue and the savings produced by your own PV system. It supports Ukrainian single-zone and dual-zone (day/night) tariffs.

## Installation

1. Copy the `custom_components/energy_cost` folder into your Home Assistant `config/custom_components/` directory.
2. Restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration** and search for **Energy Cost**.
4. Fill in the form and select your cumulative energy sensors.

The integration is configured entirely from the UI, and the same fields are available later through **Configure** on the integration card.

## Configuration fields

| Field | Required | Default | Description |
| --- | --- | --- | --- |
| Grid import energy sensor | Yes | — | Cumulative grid import energy sensor in kWh (`state_class: total_increasing`). |
| Grid export energy sensor | No | — | Cumulative grid export energy sensor in kWh. |
| PV production energy sensor | No | — | Cumulative PV production sensor in kWh, used for "saved by PV". |
| Tariff mode | Yes | `single` | `single` for one price, `dual` for day/night prices. |
| Single-zone price per kWh | Yes | `4.32` | Price used when the tariff mode is `single`. |
| Day price per kWh | Yes | `4.32` | Day price used when the tariff mode is `dual`. |
| Night price per kWh | Yes | `2.16` | Night price used when the tariff mode is `dual`. |
| Night window start | Yes | `23:00` | Local time when the night tariff starts. |
| Night window end | Yes | `07:00` | Local time when the night tariff ends. |
| Export price per kWh | Yes | `0.0` | Revenue per exported kWh; `0` if export is not compensated. |
| Currency | Yes | `₴` | Currency symbol shown on every money sensor. |
| Billing period start day | Yes | `1` | Day of the month (1–28) when the billing period starts. |

Sensors are accepted when they belong to the `sensor` domain and report `kWh`, `Wh` or `MWh`. Values are normalized to kWh internally.

### Ukrainian dual-zone example

A typical Ukrainian dual-zone tariff with a night rate from 23:00 to 07:00:

| Setting | Value |
| --- | --- |
| Tariff mode | `dual` |
| Day price per kWh | `4.32` |
| Night price per kWh | `2.16` |
| Night window start | `23:00` |
| Night window end | `07:00` |
| Currency | `₴` |

Every kWh is priced with the tariff that is active at the moment the delta is processed. Day-to-day consumption between 23:00 and 07:00 is therefore charged at 2.16 ₴/kWh and the rest at 4.32 ₴/kWh.

## Entities

All entities use the device name from the integration entry (by default `Energy Cost`) as a prefix. Entity IDs are generated from the device and entity names in your Home Assistant language, so the IDs below reflect the default English names. Copy the actual IDs from **Settings → Devices & services → Entities** if your installation uses different names.

| Entity ID (English default) | Unit | Description |
| --- | --- | --- |
| `sensor.energy_cost_cost_billing_period` | currency | Net cost of the current billing period (`import cost − export revenue`). |
| `sensor.energy_cost_import_cost_billing_period` | currency | Import cost accumulated in the current billing period. |
| `sensor.energy_cost_export_revenue_billing_period` | currency | Export revenue accumulated in the current billing period. |
| `sensor.energy_cost_pv_savings_billing_period` | currency | Money saved by PV self-consumption in the billing period. |
| `sensor.energy_cost_cost_today` | currency | Net cost since local midnight. |
| `sensor.energy_cost_cost_this_month` | currency | Net cost for the current calendar month, independent of the billing period. |
| `sensor.energy_cost_total_cost` | currency | Lifetime net cost since the integration was added. |
| `sensor.energy_cost_current_price` | currency/kWh | Import price active right now. |
| `sensor.energy_cost_current_tariff` | — | `day`, `night` or `single`. |

Every money sensor exposes the `currency` and `tariff_mode` attributes. The period cost sensor also exposes `period_start`.

## Lovelace card

```yaml
type: entities
title: Energy Cost
entities:
  - entity: sensor.energy_cost_cost_today
    name: Today
  - entity: sensor.energy_cost_cost_this_month
    name: This month
  - entity: sensor.energy_cost_cost_billing_period
    name: Billing period
  - entity: sensor.energy_cost_import_cost_billing_period
    name: Import cost
  - entity: sensor.energy_cost_export_revenue_billing_period
    name: Export revenue
  - entity: sensor.energy_cost_pv_savings_billing_period
    name: PV savings
  - entity: sensor.energy_cost_current_price
    name: Current price
  - entity: sensor.energy_cost_current_tariff
    name: Tariff
```

## How the calculations work

- On every update (every 60 seconds) and whenever a tracked sensor changes, the integration reads the cumulative values, converts them to kWh and computes `delta = current − previous`.
- A negative delta is treated as a counter reset or sensor replacement: the baseline is re-based and no negative cost is added.
- Deltas are priced with the tariff that is active at the time of the update.
- The billing period starts on `month_start_day`; when the local date crosses that boundary, the period counters are reset while lifetime totals continue.
- `cost_today` resets at local midnight and `cost_month` at the start of a calendar month.
- Accumulators are stored with `homeassistant.helpers.storage.Store` under `energy_cost.<entry_id>` and written at most once every 60 seconds, plus when the integration is unloaded.

## Requirements and notes

- Energy sensors must be cumulative (`state_class: total_increasing`) and report `kWh`, `Wh` or `MWh`. Instantaneous power sensors (`W`, `kW`) are not supported.
- The integration does not create long-term statistics for the source sensors; it only reads them.
- Values are recomputed from deltas, so a restart does not double-charge energy already processed. A change that happens while Home Assistant is stopped is priced with the tariff active at the next update.
- If you change the billing start day, the current billing period restarts; lifetime totals are preserved.
