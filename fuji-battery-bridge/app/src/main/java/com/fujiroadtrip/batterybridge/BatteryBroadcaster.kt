package com.fujiroadtrip.batterybridge

import android.content.Context
import android.content.Intent

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
            putExtra("soc", values.soc.orNaN())
            putExtra("voltage", values.voltage.orNaN())
            putExtra("current", values.current.orNaN())
            putExtra("power", values.power.orNaN())
            putExtra("consumed_ah", values.consumedAh.orNaN())
            putExtra("time_to_go_minutes", values.timeToGoMinutes.orNaN())
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

fun Double?.orNaN(): Double = this ?: Double.NaN
