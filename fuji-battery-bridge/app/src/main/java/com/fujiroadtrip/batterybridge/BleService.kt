package com.fujiroadtrip.batterybridge

import android.Manifest
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.bluetooth.BluetoothManager
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanFilter
import android.bluetooth.le.ScanResult
import android.bluetooth.le.ScanSettings
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import java.util.Locale

class BleService : Service() {
    private val channelId = "fuji_battery"
    private val notificationId = 7
    private val handler = Handler(Looper.getMainLooper())
    private var scanner: android.bluetooth.le.BluetoothLeScanner? = null
    private var scanStarted = false
    private var smartShuntMac = ""
    private var advertisementKey = ByteArray(0)
    private var lastUpdateMs = 0L
    private var lastStatus = "Waiting for SmartShunt..."

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
        startForeground(notificationId, notification(lastStatus))
        handler.post(staleCheck)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        loadConfig()
        startBleScan()
        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        stopBleScan()
        handler.removeCallbacks(staleCheck)
        super.onDestroy()
    }

    private fun loadConfig() {
        val prefs = getSharedPreferences("fuji", MODE_PRIVATE)
        smartShuntMac = prefs.getString("mac", "").orEmpty().uppercase(Locale.US)
        advertisementKey = VictronDecoder.keyFromHex(prefs.getString("key", "").orEmpty()) ?: ByteArray(0)
    }

    private fun startBleScan() {
        if (scanStarted) return
        if (smartShuntMac.isBlank() || advertisementKey.size != 16) {
            setStatus("Open the app and save SmartShunt MAC/key")
            return
        }
        if (!hasBlePermissions()) {
            setStatus("Bluetooth permission denied")
            return
        }

        val adapter = try {
            (getSystemService(Context.BLUETOOTH_SERVICE) as BluetoothManager).adapter
        } catch (e: Exception) {
            null
        }
        if (adapter == null) {
            setStatus("Bluetooth not available")
            return
        }
        if (!adapter.isEnabled) {
            setStatus("Bluetooth disabled")
            return
        }

        scanner = adapter.bluetoothLeScanner
        if (scanner == null) {
            setStatus("BLE scanner unavailable")
            return
        }

        val filters = listOf(ScanFilter.Builder().setDeviceAddress(smartShuntMac).build())
        val settings = ScanSettings.Builder()
            .setScanMode(ScanSettings.SCAN_MODE_LOW_POWER)
            .setReportDelay(0L)
            .build()

        try {
            scanner?.startScan(filters, settings, scanCallback)
            scanStarted = true
            setStatus("Waiting for SmartShunt...")
        } catch (e: SecurityException) {
            setStatus("Bluetooth permission denied")
        } catch (e: IllegalArgumentException) {
            setStatus("Invalid SmartShunt MAC address")
        } catch (e: Exception) {
            setStatus("BLE scan failed")
        }
    }

    private fun stopBleScan() {
        if (!scanStarted) return
        try {
            scanner?.stopScan(scanCallback)
        } catch (e: Exception) {
            // The scanner can already be gone when Android tears down Bluetooth.
        }
        scanStarted = false
    }

    private val scanCallback = object : ScanCallback() {
        override fun onScanResult(callbackType: Int, result: ScanResult) {
            handleScanResult(result)
        }

        override fun onBatchScanResults(results: MutableList<ScanResult>) {
            results.forEach(::handleScanResult)
        }

        override fun onScanFailed(errorCode: Int) {
            scanStarted = false
            setStatus("BLE scan failed ($errorCode)")
        }
    }

    private fun handleScanResult(result: ScanResult) {
        val manufacturerData = result.scanRecord?.manufacturerSpecificData?.get(VICTRON_COMPANY_ID)
        when (val decoded = VictronDecoder.decodeBatteryMonitor(manufacturerData, advertisementKey)) {
            is DecodeResult.Success -> {
                lastUpdateMs = System.currentTimeMillis()
                broadcastToMacroDroid(decoded.values, result.rssi, lastUpdateMs)
                setStatus(formatValues(decoded.values, lastUpdateMs))
            }
            is DecodeResult.Failure -> {
                if (decoded.reason == "Encryption key mismatch") {
                    setStatus("Invalid encryption key")
                } else if (lastUpdateMs == 0L) {
                    setStatus(decoded.reason)
                }
            }
        }
    }

    private fun broadcastToMacroDroid(values: BatteryValues, rssi: Int, updatedMs: Long) {
        val intent = Intent("com.fujiroadtrip.BATTERY_UPDATE").apply {
            setPackage("com.arlosoft.macrodroid")
            putExtra("soc", values.soc.orNaN())
            putExtra("voltage", values.voltage.orNaN())
            putExtra("current", values.current.orNaN())
            putExtra("power", values.power.orNaN())
            putExtra("consumed_ah", values.consumedAh.orNaN())
            putExtra("time_to_go_minutes", values.timeToGoMinutes.orNaN())
            putExtra("rssi", rssi)
            putExtra("updated_ms", updatedMs)
        }
        sendBroadcast(intent)
    }

    private fun formatValues(values: BatteryValues, updatedMs: Long): String {
        val ageSeconds = ((System.currentTimeMillis() - updatedMs) / 1000).coerceAtLeast(0)
        return "${values.soc.format(1)}% - ${values.voltage.format(2)} V - " +
            "${values.current.format(1)} A - updated ${ageSeconds}s ago"
    }

    private fun setStatus(text: String) {
        lastStatus = text
        try {
            getSystemService(NotificationManager::class.java).notify(notificationId, notification(text))
        } catch (e: SecurityException) {
            // Notification permission can be denied on Android 13+; the service still keeps scanning.
        }
    }

    private fun notification(text: String): Notification {
        val contentIntent = PendingIntent.getActivity(
            this,
            0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        return Notification.Builder(this, channelId)
            .setContentTitle("Fuji Battery Bridge")
            .setContentText(text)
            .setSmallIcon(android.R.drawable.stat_sys_data_bluetooth)
            .setContentIntent(contentIntent)
            .setOngoing(true)
            .build()
    }

    private fun createNotificationChannel() {
        val manager = getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(
            NotificationChannel(channelId, "Fuji Battery Bridge", NotificationManager.IMPORTANCE_LOW)
        )
    }

    private fun hasBlePermissions(): Boolean {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            return checkSelfPermission(Manifest.permission.BLUETOOTH_SCAN) == PackageManager.PERMISSION_GRANTED &&
                checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT) == PackageManager.PERMISSION_GRANTED
        }
        return checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED
    }

    private val staleCheck = object : Runnable {
        override fun run() {
            if (lastUpdateMs > 0L) {
                val ageMs = System.currentTimeMillis() - lastUpdateMs
                if (ageMs > STALE_AFTER_MS && !lastStatus.startsWith("Stale")) {
                    setStatus("Stale data - last update ${ageMs / 1000}s ago")
                }
            }
            handler.postDelayed(this, STALE_CHECK_MS)
        }
    }

    companion object {
        private const val VICTRON_COMPANY_ID = 0x02E1
        private const val STALE_AFTER_MS = 60_000L
        private const val STALE_CHECK_MS = 15_000L
    }
}

private fun Double?.orNaN(): Double = this ?: Double.NaN

private fun Double?.format(decimals: Int): String {
    return if (this == null || this.isNaN()) "--" else "%.${decimals}f".format(Locale.US, this)
}
