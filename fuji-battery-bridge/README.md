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

Implemented in this first iteration:

- Foreground service with low-power BLE scanning
- Local-only SmartShunt MAC and 128-bit Victron Instant Readout key storage
- Victron manufacturer data filtering, company ID `0x02E1`
- Battery Monitor record decoding for SmartShunt-style packets
- Notification diagnostics for waiting, Bluetooth off, permission denied, invalid key, scan failure, malformed packet, and stale data
- Broadcast to MacroDroid with the agreed action and extras
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
82.0% - 13.28 V - -1.8 A - updated 0s ago
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
rssi
updated_ms
```

Suggested MacroDroid global variables for the next step:

```text
fuji_battery_soc
fuji_battery_voltage
fuji_battery_current
fuji_battery_power
fuji_battery_consumed_ah
fuji_battery_ttg
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
