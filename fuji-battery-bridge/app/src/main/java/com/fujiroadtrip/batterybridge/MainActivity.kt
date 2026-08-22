package com.fujiroadtrip.batterybridge

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.text.InputType
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import java.util.Locale

class MainActivity : Activity() {
    private lateinit var mac: EditText
    private lateinit var key: EditText

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
            text = "STOP"
            setOnClickListener { stopService(Intent(this@MainActivity, BleService::class.java)) }
        })
        layout.addView(TextView(this).apply {
            text = "\nMacroDroid intent:\ncom.fujiroadtrip.BATTERY_UPDATE\n\n" +
                "Extras:\nsoc, voltage, current, power, consumed_ah, time_to_go_minutes, rssi, updated_ms"
        })

        setContentView(layout)
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
    }
}
