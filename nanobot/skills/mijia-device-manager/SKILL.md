---
name: mijia-device-manager
description: Manage and control Xiaomi/Mijia smart home devices using the mijiaAPI CLI. Use this skill whenever the user wants to control or query smart home devices — especially robot vacuums (check status, battery level, start/stop cleaning), but also lights, plugs, air purifiers, and any Mi Home device. Triggers on requests like "start vacuuming", "stop the robot", "is the vacuum charging?", "what's the battery level?", "turn on the light", "set brightness", or any Xiaomi home automation task.
---

# Mijia Device Manager

Controls Xiaomi/Mijia smart home devices via the [mijiaAPI](https://github.com/Do1e/mijia-api) CLI (Xiaomi cloud API).

## Prerequisites

```bash
pip install mijiaAPI
```

First-time login (scan QR code with Mijia app):
```bash
python -m mijiaAPI --list_homes
```

---

## Robot Vacuum

These examples use the **Mijia Robot Vacuum M30 S** (`xiaomi.vacuum.d103cn`) as a reference. The property and action names should work for most recent Xiaomi vacuums — if not, run `--get_device_info YOUR_MODEL` to find the exact names.

First, get your vacuum's `did`:
```bash
python -m mijiaAPI -l
```

### Check status and battery

```bash
python -m mijiaAPI get --did "YOUR_DID" --prop_name "status"
python -m mijiaAPI get --did "YOUR_DID" --prop_name "battery-level"
```

Status values:

| Value | Meaning |
|---|---|
| 1 | Sweeping |
| 2 | Idle |
| 3 | Paused |
| 5 | Returning to dock |
| 6 | Charging |
| 7 | Mopping |
| 8 | Drying mop |
| 9 | Washing mop |
| 12 | Sweeping + Mopping |
| 13 | Charging complete |

### Start vacuuming

```bash
python -m mijiaAPI action --did "YOUR_DID" --action_name "start-sweep"
```

### Stop vacuuming and return to dock

```bash
# Stop current task entirely and return to dock (recommended when disturbing others)
python -m mijiaAPI action --did "YOUR_DID" --action_name "stop-clean"
python -m mijiaAPI action --did "YOUR_DID" --action_name "start-charge"
```

> `stop-sweeping` only pauses; `stop-clean` fully stops the task. Use `start-charge` to send it home.

---

## Other Devices (Lights, Plugs, etc.)

```bash
# List all devices
python -m mijiaAPI -l

# Check what a device supports
python -m mijiaAPI --get_device_info DEVICE_MODEL

# Get / set properties
python -m mijiaAPI get --did "YOUR_DID" --prop_name "brightness"
python -m mijiaAPI set --did "YOUR_DID" --prop_name "on" --value True
python -m mijiaAPI set --did "YOUR_DID" --prop_name "brightness" --value 50
python -m mijiaAPI set --did "YOUR_DID" --prop_name "color-temperature" --value 4000

# Run a scene
python -m mijiaAPI --run_scene "回家"
```

---

## Troubleshooting

**Auth failed:** `rm ~/.config/mijia-api/auth.json` then re-login with `python -m mijiaAPI --list_homes`.

**Property/action not found:** Run `--get_device_info DEVICE_MODEL` to see exactly what the device supports.

**Device offline:** Check power and network; verify it appears in the Mijia app.

**References:** [mijiaAPI GitHub](https://github.com/Do1e/mijia-api) · [Mijia Spec](https://home.miot-spec.com/)
