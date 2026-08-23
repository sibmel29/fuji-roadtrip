package com.fujiroadtrip.batterybridge

import android.content.Context
import java.util.Locale

object BatterySnapshotStore {
    private const val PREFS_NAME = "fuji"
    private const val KEY_STATUS = "snapshot_status"
    private const val KEY_SOC = "snapshot_soc"
    private const val KEY_VOLTAGE = "snapshot_voltage"
    private const val KEY_CURRENT = "snapshot_current"
    private const val KEY_POWER = "snapshot_power"
    private const val KEY_CONSUMED_AH = "snapshot_consumed_ah"
    private const val KEY_TTG = "snapshot_ttg"
    private const val KEY_STARTER_VOLTAGE = "snapshot_starter_voltage"
    private const val KEY_AUX_MODE = "snapshot_aux_mode"
    private const val KEY_RSSI = "snapshot_rssi"
    private const val KEY_UPDATED_MS = "snapshot_updated_ms"
    private const val KEY_BROADCAST_COUNT = "snapshot_broadcast_count"

    fun save(
        context: Context,
        values: BatteryValues,
        rssi: Int,
        updatedMs: Long,
        broadcastCount: Int,
        status: String
    ) {
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE).edit()
            .putString(KEY_STATUS, status)
            .putString(KEY_SOC, values.soc.display(1))
            .putString(KEY_VOLTAGE, values.voltage.display(2))
            .putString(KEY_CURRENT, values.current.display(2))
            .putString(KEY_POWER, values.power.display(2))
            .putString(KEY_CONSUMED_AH, values.consumedAh.display(2))
            .putString(KEY_TTG, values.timeToGoMinutes.display(0))
            .putString(KEY_STARTER_VOLTAGE, values.starterVoltage.display(2))
            .putString(KEY_AUX_MODE, auxModeLabel(values.auxMode))
            .putInt(KEY_RSSI, rssi)
            .putLong(KEY_UPDATED_MS, updatedMs)
            .putInt(KEY_BROADCAST_COUNT, broadcastCount)
            .apply()
    }

    fun saveStatus(context: Context, status: String) {
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE).edit()
            .putString(KEY_STATUS, status)
            .apply()
    }

    fun render(context: Context): String {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        val updatedMs = prefs.getLong(KEY_UPDATED_MS, 0L)
        val age = if (updatedMs > 0L) {
            "${((System.currentTimeMillis() - updatedMs) / 1000).coerceAtLeast(0)} sec ago"
        } else {
            "--"
        }
        val rssi = if (updatedMs > 0L) "${prefs.getInt(KEY_RSSI, 0)} dBm" else "--"
        val broadcastCount = if (updatedMs > 0L) prefs.getInt(KEY_BROADCAST_COUNT, 0).toString() else "--"
        return """
            STATUS
            ${prefs.getString(KEY_STATUS, "Waiting for SmartShunt...")}

            HOUSE BATTERY
            SOC: ${prefs.getString(KEY_SOC, "--")} %
            Voltage: ${prefs.getString(KEY_VOLTAGE, "--")} V
            Current: ${prefs.getString(KEY_CURRENT, "--")} A
            Power: ${prefs.getString(KEY_POWER, "--")} W
            Consumed: ${prefs.getString(KEY_CONSUMED_AH, "--")} Ah
            Time remaining: ${prefs.getString(KEY_TTG, "--")} min

            STARTER BATTERY
            Voltage: ${prefs.getString(KEY_STARTER_VOLTAGE, "--")} V
            Aux mode: ${prefs.getString(KEY_AUX_MODE, "--")}

            BLE / MACRODROID
            RSSI: $rssi
            Last update: $age
            Broadcast #: $broadcastCount
        """.trimIndent()
    }

    private fun auxModeLabel(mode: Int): String = when (mode) {
        0 -> "starter voltage"
        1 -> "midpoint"
        2 -> "temperature"
        3 -> "disabled"
        else -> "unknown ($mode)"
    }
}

private fun Double?.display(decimals: Int): String {
    return if (this == null || this.isNaN()) "--" else "%.${decimals}f".format(Locale.US, this)
}
