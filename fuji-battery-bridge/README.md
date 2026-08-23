# Fuji Battery Bridge

Lightweight Android BLE bridge for a Victron SmartShunt 300A in Fuji.

Flow:

```text
Victron SmartShunt
  -> BLE Instant Readout advertisement
Fuji Battery Bridge
  -> Android broadcast Intent
MacroDroid
  -> Fuji Control drawer variables
```

The app passively scans Victron BLE advertisements. It does not connect to the SmartShunt.

## Current Status

Implemented:

- Foreground service with low-power BLE scanning
- Local-only SmartShunt MAC and 128-bit Victron Instant Readout key storage
- Victron manufacturer data filtering, company ID `0x02E1`
- Battery Monitor record decoding for SmartShunt-style packets
- Notification diagnostics for waiting, Bluetooth off, permission denied, invalid key, scan failure, malformed packet, and stale data
- Unscoped custom broadcast to MacroDroid with the agreed action and extras
- `SEND TEST BROADCAST` button for MacroDroid receiver debugging without BLE packets
- Broadcast counter in the notification and `broadcast_count` extra
- Starter battery voltage broadcast from the SmartShunt aux input when Aux input is configured as starter battery voltage
- GitHub Actions debug APK build

The decoder follows Victron's published Bluetooth advertising / extra manufacturer data layout for Battery Monitor records:

- TTG: 16 bits, minutes
- Voltage: signed 16 bits, 0.01 V
- Alarm reason: 16 bits
- Aux value: 16 bits
- Aux mode: 2 bits
- Current: signed 22 bits, 0.001 A
- Consumed Ah: unsigned 20 bits, displayed as negative 0.1 Ah
- SOC: unsigned 10 bits, 0.1 %

## Secrets

Do not commit the SmartShunt MAC address or advertisement key.

The app asks for both values on the phone and stores them in Android app-private `SharedPreferences`.

Ignored local/private files include:

- `local.properties`
- `secrets.properties`
- `*.jks`
- `*.keystore`
- `*.apk`
- `captures/`

## Configure On Android

1. In VictronConnect, enable Instant Readout for the SmartShunt.
2. Copy the MAC address and 32-character advertisement key from the Instant Readout details.
3. Open Fuji Battery Bridge.
4. Paste the MAC and key.
5. Tap `SAVE + START`.
6. Grant Nearby Devices and notification permissions.
7. Close or disconnect VictronConnect while testing, because connected VictronConnect sessions can stop Instant Readout advertisements.

Expected notification once packets decode:

```text
Fuji Battery Bridge
BLE OK - MacroDroid #153 - 82.0% - 13.28 V - -32 W - start 12.62 V - 0s ago
```

## MacroDroid Broadcast

Action:

```text
com.fujiroadtrip.BATTERY_UPDATE
```

Extras:

```text
soc
voltage
current
power
consumed_ah
time_to_go_minutes
starter_voltage
aux_mode
rssi
updated_ms
broadcast_count
source
```

The main numeric extras are still sent as Android numeric types. Live SmartShunt packets
are throttled to one MacroDroid broadcast per minute, which keeps the drawer useful
without notification spam. `broadcast_count` and `source` are debug helpers so
MacroDroid can prove that it received a specific packet.

`starter_voltage` is populated when the SmartShunt aux input is set to starter
battery voltage in VictronConnect. `aux_mode` is included for debugging that
configuration.

Version `0.2` deliberately sends a normal custom broadcast without
`setPackage("com.arlosoft.macrodroid")`, because the MacroDroid log showed no receive
activity for `com.fujiroadtrip.BATTERY_UPDATE`. MacroDroid's receiver macro should
listen for exactly:

```text
com.fujiroadtrip.BATTERY_UPDATE
```

For the first test, add only a diagnostic notification action in MacroDroid, then tap
`SEND TEST BROADCAST` in the app. Once the trigger fires, map the extras into variables.

Suggested MacroDroid global variables for the next step:

```text
fuji_battery_soc
fuji_battery_voltage
fuji_battery_current
fuji_battery_power
fuji_battery_consumed_ah
fuji_battery_ttg
fuji_battery_starter_voltage
fuji_battery_aux_mode
fuji_battery_rssi
fuji_battery_updated
```

## Build With GitHub Actions

Push this project to GitHub, then run:

```text
Actions -> Build Fuji Battery Bridge -> Run workflow
```

Download the `Fuji-Battery-Bridge-APK` artifact and install `app-debug.apk`.

## Build Locally

No global Gradle install is required:

```bash
./gradlew :app:assembleDebug
```

The APK will be written to:

```text
app/build/outputs/apk/debug/app-debug.apk
```

## First Real-Device Validation

Before wiring this into the Fuji Control drawer, compare the notification values against VictronConnect:

- SOC
- Battery voltage
- Battery current

If the app sees the SmartShunt but shows `Invalid encryption key`, copy the key again from VictronConnect and check it is exactly 32 hex characters.

If it keeps waiting forever, confirm Bluetooth is enabled, Instant Readout is enabled, the MAC address is correct, and VictronConnect is not actively connected.
