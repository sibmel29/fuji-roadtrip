package com.fujiroadtrip.batterybridge

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.text.InputType
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import java.util.Locale

class MainActivity : Activity() {
    private lateinit var mac: EditText
    private lateinit var key: EditText
    private lateinit var dashboard: TextView
    private val handler = Handler(Looper.getMainLooper())
    private val dashboardRefresh = object : Runnable {
        override fun run() {
            refreshDashboard()
            handler.postDelayed(this, DASHBOARD_REFRESH_MS)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val prefs = getSharedPreferences("fuji", MODE_PRIVATE)
        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(40, 50, 40, 40)
        }

        layout.addView(TextView(this).apply {
            text = "Fuji Battery Bridge"
            textSize = 28f
        })
        layout.addView(TextView(this).apply {
            text = "Victron SmartShunt Instant Readout -> MacroDroid"
            textSize = 16f
        })

        mac = EditText(this).apply {
            hint = "MAC AA:BB:CC:DD:EE:FF"
            setText(prefs.getString("mac", ""))
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_CAP_CHARACTERS
        }
        key = EditText(this).apply {
            hint = "32-character encryption key"
            setText(prefs.getString("key", ""))
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD
        }
        layout.addView(mac)
        layout.addView(key)

        layout.addView(Button(this).apply {
            text = "SAVE + START"
            setOnClickListener { saveAndStart(prefs) }
        })
        layout.addView(Button(this).apply {
            text = "SEND TEST BROADCAST"
            setOnClickListener { sendTestBroadcast() }
        })
        layout.addView(Button(this).apply {
            text = "STOP"
            setOnClickListener {
                stopService(Intent(this@MainActivity, BleService::class.java))
                BatterySnapshotStore.saveStatus(this@MainActivity, "Stopped")
                refreshDashboard()
            }
        })
        layout.addView(TextView(this).apply {
            text = "\nLive values"
            textSize = 20f
        })
        dashboard = TextView(this).apply {
            text = BatterySnapshotStore.render(this@MainActivity)
            textSize = 16f
            typeface = android.graphics.Typeface.MONOSPACE
        })
        layout.addView(dashboard)
        layout.addView(TextView(this).apply {
            text = "\nMacroDroid intent:\ncom.fujiroadtrip.BATTERY_UPDATE\n\n" +
                "Extras:\nsoc, voltage, current, power, consumed_ah, time_to_go_minutes, " +
                "starter_voltage, aux_mode, rssi, updated_ms\n\n" +
                "The app display refreshes while open. MacroDroid broadcasts are rounded " +
                "to two decimals and sent once per minute."
        })

        setContentView(ScrollView(this).apply { addView(layout) })
    }

    override fun onResume() {
        super.onResume()
        handler.post(dashboardRefresh)
    }

    override fun onPause() {
        handler.removeCallbacks(dashboardRefresh)
        super.onPause()
    }

    private fun refreshDashboard() {
        if (::dashboard.isInitialized) {
            dashboard.text = BatterySnapshotStore.render(this)
        }
    }

    private fun saveAndStart(prefs: android.content.SharedPreferences) {
        val normalizedMac = mac.text.toString().trim().uppercase(Locale.US)
        val normalizedKey = key.text.toString().trim().replace(" ", "").replace(":", "").lowercase(Locale.US)
        if (!Regex("^([0-9A-F]{2}:){5}[0-9A-F]{2}$").matches(normalizedMac) ||
            VictronDecoder.keyFromHex(normalizedKey) == null
        ) {
            Toast.makeText(this, "Check MAC/key format", Toast.LENGTH_LONG).show()
            return
        }

        prefs.edit().putString("mac", normalizedMac).putString("key", normalizedKey).apply()
        requestStart()
    }

    private fun sendTestBroadcast() {
        val updatedMs = System.currentTimeMillis()
        val values = BatteryValues(
            soc = 66.6,
            voltage = 12.34,
            current = -1.23,
            power = -15.18,
            consumedAh = -4.5,
            timeToGoMinutes = 321.0,
            starterVoltage = 12.34,
            auxMode = 0,
            modelId = 0
        )
        val count = BatteryBroadcaster.sendBatteryUpdate(this, values, -55, updatedMs)
        BatterySnapshotStore.save(this, values, -55, updatedMs, count, "TEST broadcast sent")
        refreshDashboard()
        Toast.makeText(
            this,
            "TEST broadcast sent (#$count): -15 W, start 12.34 V",
            Toast.LENGTH_LONG
        ).show()
    }

    private fun requestStart() {
        val permissions = mutableListOf<String>()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            if (checkSelfPermission(Manifest.permission.BLUETOOTH_SCAN) != PackageManager.PERMISSION_GRANTED) {
                permissions.add(Manifest.permission.BLUETOOTH_SCAN)
            }
            if (checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT) != PackageManager.PERMISSION_GRANTED) {
                permissions.add(Manifest.permission.BLUETOOTH_CONNECT)
            }
        } else if (checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) != PackageManager.PERMISSION_GRANTED) {
            permissions.add(Manifest.permission.ACCESS_FINE_LOCATION)
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) {
            permissions.add(Manifest.permission.POST_NOTIFICATIONS)
        }

        if (permissions.isEmpty()) {
            startForegroundService(Intent(this, BleService::class.java))
        } else {
            requestPermissions(permissions.toTypedArray(), REQUEST_PERMISSIONS)
        }
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode != REQUEST_PERMISSIONS) return
        if (grantResults.isNotEmpty() && grantResults.all { it == PackageManager.PERMISSION_GRANTED }) {
            startForegroundService(Intent(this, BleService::class.java))
        } else {
            Toast.makeText(this, "Bluetooth permissions are required", Toast.LENGTH_LONG).show()
        }
    }

    companion object {
        private const val REQUEST_PERMISSIONS = 42
        private const val DASHBOARD_REFRESH_MS = 1_000L
    }
}
