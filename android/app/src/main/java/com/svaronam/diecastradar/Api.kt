package com.svaronam.diecastradar

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

/** HTTP mínimo con HttpURLConnection (sin librerías). */
object Api {
    private const val UA = "DiecastRadar-Android/1.0"

    fun get(url: String, readTimeoutMs: Int = 20_000): String = request(url, "GET", readTimeoutMs)

    fun post(url: String): String = request(url, "POST", 20_000)

    private fun request(url: String, method: String, readTimeoutMs: Int): String {
        val conn = URL(url).openConnection() as HttpURLConnection
        try {
            conn.requestMethod = method
            conn.connectTimeout = 15_000
            conn.readTimeout = readTimeoutMs
            conn.setRequestProperty("Accept", "application/json")
            conn.setRequestProperty("User-Agent", UA)
            if (method == "POST") {
                conn.doOutput = true
                conn.outputStream.use { it.write(ByteArray(0)) }
            }
            val code = conn.responseCode
            val stream = if (code in 200..299) conn.inputStream else conn.errorStream
            val body = stream?.bufferedReader()?.use { it.readText() } ?: ""
            if (code !in 200..299) throw IOException("HTTP $code $body")
            return body
        } finally {
            conn.disconnect()
        }
    }

    /** Descarga la foto del coche, reducida para que la notificación no pese. */
    fun bitmap(url: String, maxSide: Int = 1024): Bitmap? {
        return try {
            val conn = URL(url).openConnection() as HttpURLConnection
            conn.connectTimeout = 10_000
            conn.readTimeout = 15_000
            conn.setRequestProperty("User-Agent",
                "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128 Mobile Safari/537.36")
            conn.instanceFollowRedirects = true
            val bytes = try {
                if (conn.responseCode !in 200..299) return null
                conn.inputStream.use { it.readBytes() }
            } finally {
                conn.disconnect()
            }
            if (bytes.size > 12_000_000) return null
            val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
            BitmapFactory.decodeByteArray(bytes, 0, bytes.size, bounds)
            var sample = 1
            while (bounds.outWidth / sample > maxSide || bounds.outHeight / sample > maxSide) sample *= 2
            BitmapFactory.decodeByteArray(bytes, 0, bytes.size,
                BitmapFactory.Options().apply { inSampleSize = sample })
        } catch (e: Exception) {
            null
        }
    }
}
