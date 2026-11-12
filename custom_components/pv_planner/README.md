# PV Planner

PV Planner turns a PV + battery + grid installation into a small set of
**decision sensors**. It answers three questions:

1. How much solar energy will be produced today and tomorrow?
2. How much spare power is available right now?
3. Does the battery hold enough reserve to get through the night?

The integration is **read-only**: it never switches devices, chargers or
loads. Automations use its sensors and decide what to do.

## How it works

- The solar forecast comes from the free [Forecast.Solar](https://forecast.solar)
  estimate API. No API key is needed. The response is polled at most once per
  hour (the free tier allows 12 requests per hour), configurable up to once per
  day in the options.
- Live values are read from the sensors you select. All powers are converted to
  watts, then split according to the sign conventions you configure:

  ```
  home load      = pv_now + battery_discharge + import - battery_charge - export
  power surplus  = pv_now - home load - battery_charge
  reserve needed = night_consumption_kwh
  reserve floor  = night_consumption_kwh + min_reserve_percent% of capacity
  ```

  `power_surplus` is the power that can go to an **additional** load right now
  without importing and without discharging the battery. It may be negative.

- The advice sensor combines everything into one state: `surplus`, `hold`,
  `reserve_low` or `no_data`.

## Installation

1. Copy the `pv_planner` folder into `/config/custom_components/` so the path is
   `/config/custom_components/pv_planner/manifest.json`.
2. Restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration**, search for
   **PV Planner** and fill in the form.

The integration supports a single entry. All settings can be changed later via
**Configure** on the integration card.

## Configuration

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| Latitude | float | HA latitude | Site latitude for Forecast.Solar. |
| Longitude | float | HA longitude | Site longitude for Forecast.Solar. |
| Panel tilt | int (0–90°) | 35 | `declination`: 0 is flat, 90 is vertical. |
| Panel azimuth | int (−180…180°) | 0 | Forecast.Solar convention: 0 = south, −90 = east, 90 = west. |
| Peak power | float (kWp) | 5.0 | Combined peak power of all panels. |
| PV power sensor | sensor (W/kW) | — | Current total PV power. |
| Grid power sensor | sensor (W/kW) | — | Signed grid power. |
| Grid power sign | select | `negative_is_import` | `negative_is_import` or `positive_is_import`. |
| Battery power sensor | sensor (W/kW) | — | Signed battery power. |
| Battery power sign | select | `positive_is_charging` | `positive_is_charging` or `negative_is_charging`. |
| Battery charge sensor | sensor (%) | — | State of charge. |
| Battery capacity | float (kWh) | 5.0 | Usable capacity. |
| Minimum reserve | float (%) | 20 | Share of capacity that must always stay in reserve. |
| Night consumption | float (kWh) | 2.0 | Energy needed between sunset and sunrise. |
| Surplus threshold | int (W) | 200 | Minimum surplus for `binary_sensor.pv_planner_surplus_available`. |
| Forecast poll interval | int (min) | 60 | Options only. Minimum 60 minutes. |

Entity units are validated: power sensors must report W, kW or MW (a sensor
without a unit is assumed to be in W), and the state-of-charge sensor must
report `%`.

## Entities

Entity IDs assume the default device name **PV Planner**; renaming the device
changes them.

| Entity | Unit | Meaning |
| --- | --- | --- |
| `sensor.pv_planner_pv_forecast_today` | kWh | Forecast energy for today. |
| `sensor.pv_planner_pv_forecast_tomorrow` | kWh | Forecast energy for tomorrow. |
| `sensor.pv_planner_pv_forecast_remaining_today` | kWh | Forecast energy from now until midnight. |
| `sensor.pv_planner_pv_forecast_now` | W | Interpolated forecast power for the current moment. |
| `sensor.pv_planner_home_load_power` | W | Computed house consumption. |
| `sensor.pv_planner_battery_charge_power` | W | Current battery charging power (`0` while discharging). |
| `sensor.pv_planner_battery_remaining_energy` | kWh | `soc% × capacity`. |
| `sensor.pv_planner_battery_reserve_needed` | kWh | Night consumption that the battery must cover. |
| `sensor.pv_planner_power_surplus` | W | Spare power available for new loads; may be negative. |
| `sensor.pv_planner_energy_advice` | text | `surplus`, `hold`, `reserve_low` or `no_data`. |
| `binary_sensor.pv_planner_surplus_available` | on/off | `power_surplus >= surplus_threshold_w`. |
| `binary_sensor.pv_planner_battery_reserve_ok` | on/off | Stored energy ≥ night consumption + minimum reserve. |

Useful attributes:

- `sensor.pv_planner_pv_forecast_today` — `curve` (today and tomorrow as
  `[{ "time": ISO timestamp, "watts": W }]`, ready for ApexCharts),
  `last_update`, `provider`.
- `sensor.pv_planner_power_surplus` — `pv_now`, `home_load`,
  `battery_charge`, `import_w`, `export_w`.
- `sensor.pv_planner_energy_advice` — `advice_text`, the translated,
  human-readable advice.
- `sensor.pv_planner_battery_reserve_needed` — `explanation`,
  `night_consumption_kwh`, `min_reserve_percent`, `battery_capacity_kwh`,
  `reserve_floor_kwh`.

## Example automation: water heater on surplus

Turn a heater on once surplus has been available for 10 minutes, and off as
soon as it disappears:

```yaml
automation:
  - alias: "Water heater on solar surplus"
    id: water_heater_solar_surplus
    triggers:
      - trigger: state
        entity_id: binary_sensor.pv_planner_surplus_available
        to: "on"
        for: "00:10:00"
      - trigger: state
        entity_id: binary_sensor.pv_planner_surplus_available
        to: "off"
    actions:
      - choose:
          - conditions:
              - condition: state
                entity_id: binary_sensor.pv_planner_surplus_available
                state: "on"
            sequence:
              - action: switch.turn_on
                target:
                  entity_id: switch.water_heater
        default:
          - action: switch.turn_off
            target:
              entity_id: switch.water_heater
    mode: single
```

## Notes and limitations

- Forecast.Solar timestamps are local site time without an offset. The site is
  expected to share Home Assistant's timezone.
- If the Forecast.Solar request fails or returns `message.type == "error"`, the
  coordinator update fails and the entities become unavailable. Live
  measurements recover as soon as the source sensors are back.
- The forecast is an estimate; shading, snow and dirty panels are not modelled.
