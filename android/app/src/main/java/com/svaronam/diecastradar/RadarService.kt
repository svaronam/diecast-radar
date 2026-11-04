package com.svaronam.diecastradar

import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import org.json.JSONArray
import org.json.JSONObject
import kotlin.concurrent.thread

/**
 * Servicio en primer plano que escucha a la Pi por Tailscale.
 * Hace "long-poll" a /api/events: la Pi responde en cuanto hay un aviso
 * (o a los 50 s sin novedades) y la app vuelve a preguntar.
 */
class RadarService : Service() {

    @Volatile private var running = false
    private var worker: Thread? = null
    private var lastState = ""

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        Notifs.ensureChannels(this)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val n = Notifs.service(this, "Conectando con la Pi…")
        if (Build.VERSION.SDK_INT >= 34) {
            startForeground(Notifs.SERVICE_ID, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE)
        } else {
            startForeground(Notifs.SERVICE_ID, n)
        }
        if (intent?.getBooleanExtra(EXTRA_RECONNECT, false) == true) {
            worker?.interrupt()  // corta la espera actual para usar el servidor nuevo
        }
        if (!running) {
            running = true
            worker = thread(name = "radar-poll", isDaemon = true) { loop() }
        }
        return START_STICKY
    }

    override fun onDestroy() {
        running = false
        worker?.interrupt()
        super.onDestroy()
    }

    private fun setState(text: String) {
        if (text != lastState) {
            lastState = text
            Notifs.updateService(this, text)
        }
    }

    private fun pause(ms: Long) {
        try { Thread.sleep(ms) } catch (_: InterruptedException) { }
    }

    private fun loop() {
        var backoff = 5_000L
        while (running) {
            val server = Prefs.server(this)
            if (server.isEmpty()) {
                setState("Abre la app y pon la dirección de la Pi")
                pause(30_000)
                continue
            }
            try {
                val cursor = Prefs.cursor(this)
                val url = if (cursor < 0) "$server/api/events"
                          else "$server/api/events?after=$cursor&wait=50"
                val json = JSONObject(Api.get(url, readTimeoutMs = 75_000))
                val arr = json.optJSONArray("events") ?: JSONArray()
                val events = (0 until arr.length()).map { arr.getJSONObject(it) }
                if (events.size > MAX_INDIVIDUAL) {
                    Notifs.digest(this, events)
                } else {
                    events.forEach { Notifs.item(this, it) }
                }
                Prefs.setCursor(this, json.optLong("last_id", cursor))
                Prefs.setLastOk(this, System.currentTimeMillis())
                val quiet = json.optBoolean("quiet")
                setState(if (quiet) "Silencio nocturno · conectado" else "Conectado a la Pi · escuchando")
                backoff = 5_000L
            } catch (e: InterruptedException) {
                if (!running) break
            } catch (e: Exception) {
                setState("Sin conexión con la Pi (¿Tailscale activo?)")
                pause(backoff)
                backoff = (backoff * 2).coerceAtMost(120_000L)
            }
        }
    }

    companion object {
        const val MAX_INDIVIDUAL = 8
        private const val EXTRA_RECONNECT = "reconnect"

        fun start(c: Context, reconnect: Boolean = false) {
            val i = Intent(c, RadarService::class.java).putExtra(EXTRA_RECONNECT, reconnect)
            c.startForegroundService(i)
        }
    }
}
