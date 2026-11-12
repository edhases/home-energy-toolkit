# Device Watchdog

A Home Assistant custom integration that watches a list of entities and tells
you when they go `unavailable` (or `unknown`) and stay that way, then tells you
again when they come back.

It is built for devices that silently drop off the network — Tuya plugs, Wi-Fi
lamps, inverter sensors, anything that exposes a state in Home Assistant.

## Features

- Watches any `entity_id`, regardless of domain or integration.
- Configurable offline threshold (default 10 minutes) and repeat interval
  (default 120 minutes).
- Notifications through the built-in persistent notification panel and/or any
  `notify.*` service (mobile app, Telegram, ntfy, …).
- Recovery notifications, so you know the device is back.
- Survives Home Assistant restarts: offline timers are persisted and restored.
- Summary sensors (`sensor.device_watchdog_devices_offline`,
  `sensor.device_watchdog_offline_devices`) and a
  `binary_sensor.device_watchdog_any_device_offline` problem sensor.
- Services to check immediately or to reset the tracking history.

## Installation

1. Copy the `device_watchdog` folder into
   `<config>/custom_components/device_watchdog`.
2. Restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration** and search for
   **Device Watchdog**.
4. Paste the entity IDs you want to watch (one per line or comma separated),
   adjust the thresholds and pick a notification service if you want push
   notifications.

No YAML configuration is required.

## Configuration

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| Entities to watch | text (multi-line) | — | Entity IDs, one per line or comma separated. Each entry must exist in the entity registry or the state machine. |
| Offline threshold | minutes (min 1) | 10 | How long an entity must stay offline before the first notification. |
| Repeat notification interval | minutes (min 5) | 120 | How often to repeat the notification while the entity is still offline. |
| Notification service | text | — | Optional `notify.*` service, for example `notify.24117rn76e`. |
| Create persistent notifications | boolean | on | Also show a notification in the Home Assistant notification panel. |
| Treat `unknown` as offline | boolean | off | Also treat the `unknown` state as offline. Useful for sensors that lose their value without becoming `unavailable`. |
| Startup grace period | minutes | 5 | Do not notify during the first minutes after the integration is loaded. |

All fields can be changed later through
**Settings → Devices & services → Device Watchdog → Configure** (the options
flow exposes exactly the same fields).

Entities that are not in the entity registry and have no state at the moment of
configuration are rejected with a list of the unknown IDs.

## Entities

| Entity | Type | Description |
| --- | --- | --- |
| `sensor.device_watchdog_devices_offline` | sensor | Number of watched entities that are currently offline. Icon `mdi:lan-disconnect`. |
| `sensor.device_watchdog_offline_devices` | sensor | Comma-separated friendly names of the offline entities, or `none`. |
| `binary_sensor.device_watchdog_any_device_offline` | binary sensor | On when at least one watched entity is offline. `device_class: problem`. |

Entity IDs are prefixed with the integration's device name (`Device Watchdog`)
because the entities use Home Assistant's "has entity name" convention. Rename
the device if you prefer a shorter prefix; existing entity IDs keep their value
unless you change them manually.

Both sensors expose the same attributes:

```yaml
watched_count: 5
offline:
  - entity_id: sensor.kitchen_plug_power
    since: "2026-11-12T09:41:12+00:00"
    minutes: 143
```

Entities are updated every 30 seconds, and immediately after a service call.

## Services

### `device_watchdog.check_now`

Force an immediate evaluation instead of waiting for the next poll.

```yaml
action: device_watchdog.check_now
# data:
#   entry_id: 01J9Z0X6V8T4R2M3N5P7Q9S1B3   # optional, defaults to all entries
```

### `device_watchdog.reset`

Clear the offline timers and notification history. Entities that are offline at
the moment of the reset start counting from zero again and are re-notified only
after a full offline threshold.

```yaml
action: device_watchdog.reset
target: {}
# data:
#   entry_id: 01J9Z0X6V8T4R2M3N5P7Q9S1B3   # optional, defaults to all entries
```

Both services accept an optional `entry_id`, selectable in the UI. Without it
they act on every Device Watchdog config entry. An unknown `entry_id` raises a
translated service validation error.

## How it works

Every 30 seconds the integration reads the current state of each watched entity
from the state machine. Missing states, `unavailable`, and (optionally)
`unknown` count as offline.

1. The first time an entity is seen offline, `offline_since` is recorded and
   persisted in a `Store` file (`device_watchdog.<entry_id>`).
2. When the entity has been offline for longer than the offline threshold, one
   notification is sent and the notification time is recorded.
3. While the entity stays offline, the notification is repeated once per repeat
   interval.
4. When the entity becomes available again, a recovery notification is sent if
   at least one offline notification had been sent, and the tracking state is
   cleared.

Notification channels are best effort: a missing `notify.*` service only logs a
warning, and never interrupts polling.

### Startup grace period

Home Assistant integrations often need a moment to restore their entities after
a restart, and entities can be missing or `unavailable` during that window. To
avoid false alarms, no notification is sent during the first
`ignore_startup_minutes` minutes after the integration is loaded. The offline
clock itself starts at the first observation, so devices that were already
offline before the restart keep their original `offline_since` timestamp and are
reported as soon as the grace period ends (subject to the repeat schedule).

Set the grace period to `0` to disable it.

### Persistence

`offline_since`, `last_notified` and the "already notified" flag are stored per
entity under `.storage/device_watchdog.<entry_id>`. Removing an entity from the
watched list drops its stored state on the next save.

## Notes and limitations

- The integration only reads states; it does not poll the devices themselves.
  The device integration is still responsible for detecting that the device is
  offline.
- If the `notify` service is not available when a notification is due, the
  warning is logged and the notification is skipped; it is not queued.
- A device that is removed from Home Assistant entirely (no state and no
  registry entry) is treated as offline, because the watchdog can no longer see
  it.

## Translations

English and Ukrainian UI strings are bundled, including notification texts.
Notification language follows the Home Assistant language setting.
