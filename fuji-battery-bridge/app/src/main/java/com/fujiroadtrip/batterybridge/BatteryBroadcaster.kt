package com.fujiroadtrip.batterybridge

import android.content.Context
import android.content.Intent
import kotlin.math.round

object BatteryBroadcaster {
    const val ACTION_BATTERY_UPDATE = "com.fujiroadtrip.BATTERY_UPDATE"

    private const val PREFS_NAME = "fuji"
    private const val KEY_BROADCAST_COUNT = "broadcast_count"

    fun sendBatteryUpdate(
        context: Context,
        values: BatteryValues,
        rssi: Int,
        updatedMs: Long
    ): Int {
        val count = nextBroadcastCount(context)
        val intent = Intent(ACTION_BATTERY_UPDATE).apply {
            addFlags(Intent.FLAG_RECEIVER_FOREGROUND)
            putExtra("soc", values.soc.roundedOrNaN())
            putExtra("voltage", values.voltage.roundedOrNaN())
            putExtra("current", values.current.roundedOrNaN())
            putExtra("power", values.power.roundedOrNaN())
            putExtra("consumed_ah", values.consumedAh.roundedOrNaN())
            putExtra("time_to_go_minutes", values.timeToGoMinutes.roundedOrNaN())
            putExtra("starter_voltage", values.starterVoltage.roundedOrNaN())
            putExtra("aux_mode", values.auxMode)
            putExtra("rssi", rssi)
            putExtra("updated_ms", updatedMs)
            putExtra("broadcast_count", count)
            putExtra("source", "fuji_battery_bridge")
        }
        context.sendBroadcast(intent)
        return count
    }

    private fun nextBroadcastCount(context: Context): Int {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        val count = prefs.getInt(KEY_BROADCAST_COUNT, 0) + 1
        prefs.edit().putInt(KEY_BROADCAST_COUNT, count).apply()
        return count
    }
}

fun Double?.roundedOrNaN(): Double {
    val value = this ?: return Double.NaN
    if (value.isNaN()) return Double.NaN
    return round(value * 100.0) / 100.0
}
