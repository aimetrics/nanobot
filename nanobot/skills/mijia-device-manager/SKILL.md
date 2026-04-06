name | mijia-device-manager
---|---
description | Manage and control Xiaomi/Mijia smart home devices by directly invoking mijiaAPI CLI commands to control devices via the Xiaomi cloud API. Supports features such as device discovery, power control, brightness adjustment, and color settings. Use this skill when the user needs to control Xiaomi smart devices (e.g., robot vacuum, desk lamps, light bulbs, smart plugs, etc.), retrieve the device list, or check device status.

# Mijia Device Manager

## Overview
This skill is used to manage and control Xiaomi/Mijia smart home devices. It directly invokes the [mijiaAPI](https://github.com/Do1e/mijia-api) CLI to control devices via the Xiaomi cloud API.

## Features
- Login to Xiaomi account (via QR code scan)
- Retrieve device list and home list
- Get and set device properties
- Execute device actions
- View full device status

## Prerequisites
1. Install dependencies:
```bash
pip install mijiaAPI
``` 
2. Login to Xiaomi account (required for first-time use):
```bash
python -m mijiaAPI --list_homes
``` 

## Quick Start

### 1. First-time Login
```bash
python -m mijiaAPI --list_homes
```
A QR code will be displayed after running the command. Scan it using the Mijia APP to complete the login process.

### 2. View Device List

```bash
python -m mijiaAPI -l
```

Each device entry in the output contains a `did`, which will be used in subsequent control commands.

### 3. Control Devices

```bash
# Turn on the light
python -m mijiaAPI set --did "123456789" --prop_name "on" --value True

# Set brightness
python -m mijiaAPI set --did "123456789" --prop_name "brightness" --value 50

# Get status
python -m mijiaAPI get --did "123456789" --prop_name "brightness"
```

## Command Reference

```bash
python -m mijiaAPI --help
python -m mijiaAPI get --help
python -m mijiaAPI set --help
```

**Common command examples:**

```bash
# List all devices
python -m mijiaAPI -l

# Find 'did' from the list
python -m mijiaAPI -l | grep did

# List all homes
python -m mijiaAPI --list_homes

# Get device property
python -m mijiaAPI get --did "123456789" --prop_name "brightness"

# Set device properties 
python -m mijiaAPI set --did "123456789" --prop_name "on" --value True
python -m mijiaAPI set --did "123456789" --prop_name "brightness" --value 50

# Execute scene
python -m mijiaAPI --run_scene "回家"
```

## Device Properties Reference

Common device property names:

| 属性名 | 说明 | 类型 | 示例值 |
|--------|------|------|--------|
| `on` | Power status | bool | `True`/`False` |
| `brightness` | Brightness | int | 0-100 |
| `color-temperature` | Color temperature | int | 2700-6500 |
| `color` | Color | int | RGB value |

**Note:** Different devices support different properties. Before operating, please use `--get_device_info DEVICE_MODEL` to get the device property information and confirm the actionable properties before executing control commands. The `DEVICE_MODEL` can be obtained via `--list_devices`.

**Operation Steps:**

1. Use `python -m mijiaAPI -l` to list devices and confirm the `did` and `DEVICE_MODEL`.

2. Use `python -m mijiaAPI --get_device_info DEVICE_MODEL` to get available properties and their ranges.

3. Execute `get` or `set` commands based on the property information to complete your query or control action.

## Troubleshooting
### Login Issues
**Issue: Unable to login or authentication failed**

1. Delete the authentication file and login again:
  ```bash
  rm ~/.config/mijia-api/auth.json
  python -m mijiaAPI --list_homes
  ```
2. Check if your network connection is functioning normally.

3. Verify that your Mijia APP account and password are correct.

### Device Control Issues

**Issue: Cannot find the device**

1. Confirm that the device has been added in the Mijia APP.
2. Check if the device name is correct (case-sensitive).
3. Use the `-l` command to view the exact device name.

**Issue: Do not know the `did`**

1. Use `python -m mijiaAPI -l` to list devices and locate the `did` field for the device in the output.

**Issue: Failed to set property**

1. Confirm the device supports the specific property (use `--get_device_info DEVICE_MODEL` to get property info).
2. Check if the property value falls within the correct range.
3. Confirm the device is online and the network is working.

**Issue: Want to know what properties a specific device has**

1. First use `--list_devices` to get the `DEVICE_MODEL`, and then use `--get_device_info DEVICE_MODEL` to get the property info. For example:
   ```bash
   python -m mijiaAPI --get_device_info yeelink.light.lamp27
   ```

### Get Help
- mijiaAPI GitHub: https://github.com/Do1e/mijia-api
- Mijia Spec Platform: https://home.miot-spec.com/