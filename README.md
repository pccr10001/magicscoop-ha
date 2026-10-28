# MagicScoop for Home Assistant

Home Assistant integration for MagicScoop / Gingerway cat litter boxes
(M1, M1+, M1 Pro, M1 Performance and similar models).

It talks to the official MagicScoop cloud, so you can monitor and control your
litter box from Home Assistant without the phone app.

> **Cat litter boxes only — water fountains are ignored.**

Available in English, Simplified Chinese and Traditional Chinese. The language
follows your Home Assistant UI language.

---

## ⚠️ Important: use a sub-account

**Create a separate sub-account, share your litter box to it from your main
account, and sign in to Home Assistant with that sub-account.**

MagicScoop only allows one active session per account. If you sign in somewhere
else (for example the phone app), the previous session is disconnected:

- Signing in on the phone kicks Home Assistant offline.
- Home Assistant reconnecting kicks the phone app offline.

Using a dedicated sub-account for Home Assistant avoids this completely — the
main account keeps working on your phone while Home Assistant stays connected.

---

## Installation

### HACS (recommended)

1. HACS → Integrations → menu → Custom repositories
2. Add this repository URL, category **Integration**
3. Install **MagicScoop** and restart Home Assistant

### Manual

Copy the `custom_components/magicscoop/` folder into your Home Assistant
`config/custom_components/` directory, then restart Home Assistant.

```
config/custom_components/magicscoop/
├── __init__.py
├── api.py
├── binary_sensor.py
├── brand/
│   ├── icon.png
│   └── icon@2x.png
├── button.py
├── certs.py
├── config_flow.py
├── const.py
├── coordinator.py
├── crypto.py
├── entity.py
├── manifest.json
├── mqtt_client.py
├── number.py
├── select.py
├── sensor.py
├── strings.json
├── switch.py
└── translations/
    ├── en.json
    ├── zh-Hans.json
    └── zh-Hant.json
```

---

## Setup

1. **Settings → Devices & services → Add integration → MagicScoop**
2. Enter the e-mail address of your **sub-account**. A verification code is
   sent to that mailbox.
3. Enter the verification code from the e-mail.
4. Tick the litter boxes you want to add (water fountains are not listed).
5. Done — each litter box becomes its own device.

You can add the integration multiple times to connect several accounts, and each
account can contain several litter boxes.

---

## Entities

Each litter box creates the following entities. Names are translated to your UI
language.

### Sensors

| Entity | Description |
|---|---|
| Status | Standby, occupied, clumping, auto/manual/periodic/remote cleaning, sterilizing, … |
| Sub status | Running, finished, paused, timeout, pinched, … |
| Litter level | Insufficient, less, appropriate, sufficient, full, … |
| Elapsed time | Seconds spent in the current cycle |
| Cleans this month | Number of cleans in the current month |
| Firmware version | Installed firmware version |
| Wi-Fi signal | Signal strength |
| Motor current / ToF position / Rotate angle / Rotate speed | Diagnostic values |

### Binary sensors

| Entity | Description |
|---|---|
| Cat present | A cat is inside the box |
| Waste bin full | The waste bin is full |
| Cleaning | A cleaning cycle is running |

### Buttons

| Button | Description |
|---|---|
| Start clean | Start a cleaning cycle remotely |
| Pause | Pause the current operation |
| Reset | Return to the standby position |
| Sterilize | Run the UV sterilizing cycle (UV models) |

### Selects

| Entity | Options |
|---|---|
| Clean mode | Auto / Manual / Periodic |
| Clumping time | 5 / 10 / 20 / 40 / 60 minutes |
| Periodic mode | Off / every 2, 4, 6, 8 or 12 hours |
| Sleep mode | Off / 6, 7, 8 or 9 hours |

### Switches

UV sterilize, twice dumping, vibrate scooper, disable rear PIR, step mat check,
no clean while sleeping, light during sleep, ring light off at night.

### Numbers

Periodic start/stop hour and minute, sleep start hour and minute.

> Move sensitivity and rotate sensitivity are **not** exposed, because the
> official app has no UI for them.

---

## Troubleshooting

Error messages show the text returned by the cloud whenever possible.

| Message | Cause / fix |
|---|---|
| Account not found | Wrong e-mail, or the address is not registered with MagicScoop |
| Invalid or expired verification code | Wrong code, or it expired — add the integration again to request a new one |
| Verification code must be 6 digits | Check that you copied the full code |
| Failed to connect | Network or DNS problem, or the cloud is temporarily unreachable — retry later |
| No cat litter box found on this account | Nothing has been shared to the sub-account yet (see the warning above) |

To see the full traffic log, add this to `configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.magicscoop: debug
```

---

## Known limitations

- **One session per account** — use a sub-account (see the warning above).
- Sterilize only works on models with UV support; other models may ignore it.
- A cleaning timeout (cat stays inside too long) is decided by the firmware and
  cannot be configured.
- Water fountains (F1) are not supported.

## License

MIT
