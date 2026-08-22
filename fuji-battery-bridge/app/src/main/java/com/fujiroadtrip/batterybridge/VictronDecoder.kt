package com.fujiroadtrip.batterybridge

import javax.crypto.Cipher
import javax.crypto.spec.SecretKeySpec

data class BatteryValues(
    val soc: Double?,
    val voltage: Double?,
    val current: Double?,
    val power: Double?,
    val consumedAh: Double?,
    val timeToGoMinutes: Double?,
    val modelId: Int
)

sealed class DecodeResult {
    data class Success(val values: BatteryValues) : DecodeResult()
    data class Failure(val reason: String) : DecodeResult()
}

object VictronDecoder {
    private const val PRODUCT_ADVERTISEMENT = 0x10
    private const val BATTERY_MONITOR_RECORD = 0x02

    fun decodeBatteryMonitor(manufacturerData: ByteArray?, advertisementKey: ByteArray): DecodeResult {
        val raw = manufacturerData ?: return DecodeResult.Failure("No Victron manufacturer data")
        if (advertisementKey.size != 16) return DecodeResult.Failure("Invalid 128-bit key")
        if (raw.size < 8) return DecodeResult.Failure("Victron packet too short")
        if (raw[0].u8() != PRODUCT_ADVERTISEMENT) {
            return DecodeResult.Failure("Not a Victron product advertisement")
        }
        if (raw[4].u8() != BATTERY_MONITOR_RECORD) {
            return DecodeResult.Failure("Victron packet is not a Battery Monitor record")
        }
        if (raw[7] != advertisementKey[0]) {
            return DecodeResult.Failure("Encryption key mismatch")
        }

        return try {
            val modelId = raw[2].u8() or (raw[3].u8() shl 8)
            val encryptedPayload = raw.copyOfRange(8, raw.size)
            val decrypted = decryptPayload(encryptedPayload, raw[5], raw[6], advertisementKey)
            DecodeResult.Success(parseBatteryMonitor(decrypted, modelId))
        } catch (e: Exception) {
            DecodeResult.Failure("Malformed or undecodable packet")
        }
    }

    fun parseBatteryMonitor(decrypted: ByteArray, modelId: Int): BatteryValues {
        val bits = BitReader(decrypted)
        val ttgRaw = bits.readUnsigned(16)
        val voltageRaw = bits.readSignedRaw(16)
        bits.readUnsigned(16) // Alarm reason; kept for a later UI/debug iteration.
        bits.readUnsigned(16) // Aux voltage/midpoint/temperature, depending on aux mode.
        bits.readUnsigned(2) // Aux input mode.
        val currentRaw = bits.readSignedRaw(22)
        val consumedAhRaw = bits.readUnsigned(20)
        val socRaw = bits.readUnsigned(10)

        val voltage = if (voltageRaw.unsigned == 0x7FFFL) null else voltageRaw.signed / 100.0
        val current = if (currentRaw.unsigned == 0x3FFFFFL) null else currentRaw.signed / 1000.0
        return BatteryValues(
            soc = if (socRaw == 0x3FFL) null else socRaw / 10.0,
            voltage = voltage,
            current = current,
            power = if (voltage != null && current != null) voltage * current else null,
            consumedAh = if (consumedAhRaw == 0xFFFFFL) null else -consumedAhRaw / 10.0,
            timeToGoMinutes = if (ttgRaw == 0xFFFFL) null else ttgRaw.toDouble(),
            modelId = modelId
        )
    }

    fun keyFromHex(input: String): ByteArray? {
        val cleaned = input.trim().replace(" ", "").replace(":", "").lowercase()
        if (!Regex("^[0-9a-f]{32}$").matches(cleaned)) return null
        return ByteArray(16) { index ->
            cleaned.substring(index * 2, index * 2 + 2).toInt(16).toByte()
        }
    }

    private fun decryptPayload(payload: ByteArray, nonceLow: Byte, nonceHigh: Byte, key: ByteArray): ByteArray {
        val cipher = Cipher.getInstance("AES/ECB/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, SecretKeySpec(key, "AES"))

        val output = ByteArray(payload.size)
        val initialCounter = nonceLow.u8() or (nonceHigh.u8() shl 8)
        var offset = 0
        var blockIndex = 0L
        while (offset < payload.size) {
            val counterBlock = littleEndianCounterBlock(initialCounter.toLong() + blockIndex)
            val keyStream = cipher.doFinal(counterBlock)
            val length = minOf(16, payload.size - offset)
            for (i in 0 until length) {
                output[offset + i] = (payload[offset + i].toInt() xor keyStream[i].toInt()).toByte()
            }
            offset += length
            blockIndex++
        }
        return output
    }

    private fun littleEndianCounterBlock(counter: Long): ByteArray {
        val block = ByteArray(16)
        var value = counter
        for (index in block.indices) {
            block[index] = (value and 0xFF).toByte()
            value = value ushr 8
        }
        return block
    }

    private class BitReader(private val bytes: ByteArray) {
        private var position = 0

        fun readUnsigned(bitCount: Int): Long {
            if (position + bitCount > bytes.size * 8) {
                throw IllegalArgumentException("Not enough bits in Victron payload")
            }
            var value = 0L
            for (offset in 0 until bitCount) {
                val bitPosition = position + offset
                val bit = (bytes[bitPosition / 8].toInt() ushr (bitPosition % 8)) and 1
                value = value or (bit.toLong() shl offset)
            }
            position += bitCount
            return value
        }

        fun readSignedRaw(bitCount: Int): SignedValue {
            val unsigned = readUnsigned(bitCount)
            val signBit = 1L shl (bitCount - 1)
            val signed = if ((unsigned and signBit) != 0L) unsigned - (1L shl bitCount) else unsigned
            return SignedValue(unsigned, signed)
        }
    }

    private data class SignedValue(val unsigned: Long, val signed: Long)
}

private fun Byte.u8(): Int = toInt() and 0xFF
