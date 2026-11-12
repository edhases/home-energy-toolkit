# Outage Log

Outage Log is a Home Assistant custom integration that keeps a factual journal of
mains power outages. Every time the grid disappears it records an episode with:

- start and end time,
- duration,
- battery state of charge at the start and at the end,
- an optional notification when the outage starts and ends,
- an entry on a dedicated calendar.

It also exposes statistics for today and the current month, so you can see at a
glance how unreliable the grid has been.

## Requirements

- Home Assistant 2026.11 or newer.
- Python 3.13 (bundled with Home Assistant).
- A binary sensor that indicates whether grid power is present (for example a
  Shelly, a UPS status sensor, or a template sensor).
- Optional: a battery state-of-charge sensor, a battery power sensor, and a
  notify service.

## Installation

1. Copy the `custom_components/outage_log` folder into your Home Assistant
   `config/custom_components` directory.
2. Restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration** and search for
   **Outage Log**.
4. Select your grid sensor and, optionally, the battery sensors and notify
   service.

No YAML configuration is required. All settings can be changed later through
**Configure** on the integration entry.

## Configuration fields

| Field | Required | Default | Description |
| --- | --- | --- | --- |
| `grid_entity` | Yes | — | Binary sensor that reports grid presence. |
| `grid_state_present` | Yes | `on` | Which state of the binary sensor means the grid is present (`on` or `off`). |
| `battery_soc_entity` | No | — | Battery state of charge in percent. |
| `battery_power_entity` | No | — | Battery power in watts. Used to enrich the start notification. |
| `battery_capacity_kwh` | No | `5.0` | Battery capacity. Converts the state-of-charge delta into an estimated energy change. |
| `notify_service` | No | — | Notify service such as `notify.mobile_app_phone`. |
| `min_duration_seconds` | No | `30` | Outages shorter than this are ignored as blips. |

### How the minimum duration works

A grid loss is tracked immediately: the `grid_outage` binary sensor turns on and
`current_outage_duration` starts counting. The episode is only committed to the
journal after `min_duration_seconds` has passed. If the grid returns sooner,
nothing is stored, no event is fired, and no notification is sent. This keeps
short flickers out of the statistics.

## Entities

All entities use translated names and belong to a single service device.

### Sensors

| Translation key | Unit | Meaning |
| --- | --- | --- |
| `outages_today` | — | Number of outages that started today. |
| `outages_month` | — | Number of outages that started this month. |
| `outage_time_today` | min | Total outage time overlapping today, including an ongoing outage. |
| `outage_time_month` | h | Total outage time overlapping the current month, rounded to 0.1 h. |
| `last_outage_duration` | min | Duration of the most recent completed outage. |
| `last_outage_started` | timestamp | Start of the most recent episode. |
| `current_outage_duration` | min | Duration of the ongoing outage, `0` while the grid is present. |

### Binary sensor

| Translation key | Meaning |
| --- | --- |
| `grid_outage` | On while the grid is absent. Uses the problem device class. |

### Calendar

| Translation key | Meaning |
| --- | --- |
| `grid_outages` | Calendar of all recorded episodes. Ongoing outages are shown until now. |

Calendar event descriptions contain the duration and, when available, the
battery state of charge at both ends plus the estimated energy change in kWh.

## Events

The integration fires two events on the Home Assistant event bus:

| Event | When |
| --- | --- |
| `outage_log_outage_started` | An outage has passed the minimum duration and was recorded. |
| `outage_log_outage_ended` | A recorded outage ended. |

Both use the same payload:

```yaml
entry_id: 01J...
start: "2026-11-12T19:04:11+00:00"
end: "2026-11-12T19:46:52+00:00"   # null for the started event
duration_seconds: 2561.0
soc_start: 87.0
soc_end: 64.0
```

Example automation:

```yaml
alias: Report a grid outage
triggers:
  - trigger: event
    event_type: outage_log_outage_ended
actions:
  - action: notify.persistent_notification
    data:
      title: Grid outage ended
      message: >-
        Grid was absent for
        {{ (trigger.event.data.duration_seconds / 60) | round(1) }} minutes.
        Battery: {{ trigger.event.data.soc_start }}% →
        {{ trigger.event.data.soc_end }}%.
```

## Services

The integration registers no services. Use the sensors, the calendar, and the
events above. All configuration is done through the UI.

## Notifications

When an outage is recorded and `notify_service` is configured, Outage Log sends a
short message through `notify.<service>`:

- when the outage starts, including the start time and, when available, battery
  state of charge and power;
- when the outage ends, including duration, state-of-charge delta, and the
  estimated energy change in kWh.

If the notify service does not exist, a warning is written to the log and the
integration continues normally. For outages longer than five minutes, a
`persistent_notification` is also created when the outage ends.

## Persistence and restarts

Episodes are stored with Home Assistant's storage helper under the key
`outage_log.<entry_id>` (in `.storage`). The file is written after every change:
when an episode is created, when it is closed, and when startup repairs an open
episode. At most 1000 episodes are kept; the oldest are dropped first.

Reboot handling:

- If Home Assistant restarts during an outage and the last episode is still
  open, it stays open with its original start time. The outage continues to be
  counted correctly.
- If Home Assistant restarts while the grid is present and the last episode is
  open, the exact restoration time is unknown. The episode is closed with
  `end = start` as a safe fallback, so it does not remain open forever. No end
  event or notification is sent for this repair.
- If Home Assistant restarts during an outage with no open episode, tracking
  starts at boot and the episode is recorded once the minimum duration passes.

Data survives restarts and Home Assistant upgrades. Removing the integration
entry does not delete the storage file; remove
`.storage/outage_log.<entry_id>` manually if you want to start fresh.

## Lovelace example

The entity IDs below assume the entry title resolves to "Outage Log". Adjust
them to match your instance.

```yaml
type: vertical-stack
cards:
  - type: entities
    title: Grid outage journal
    show_header_toggle: false
    entities:
      - entity: binary_sensor.outage_log_grid_outage
      - entity: sensor.outage_log_current_outage_duration
      - entity: sensor.outage_log_last_outage_started
      - entity: sensor.outage_log_last_outage_duration
      - entity: sensor.outage_log_outages_today
      - entity: sensor.outage_log_outage_time_today
      - entity: sensor.outage_log_outages_month
      - entity: sensor.outage_log_outage_time_month
  - type: calendar
    initial_view: listWeek
    entities:
      - calendar.outage_log_grid_outages
```

## Notes

- The integration polls nothing. It listens to the grid sensor's state changes
  and recalculates the current duration every 30 seconds.
- Battery power is used only for notifications; it is not part of the stored
  episode schema.
- Statistics count outages by their start date. Outage time is measured as the
  overlap between an episode and the current day or month, so an outage that
  crosses midnight is split correctly.
- The calendar event summary is translated through the integration's `common`
  translations, with "Grid outage" as the English default.
