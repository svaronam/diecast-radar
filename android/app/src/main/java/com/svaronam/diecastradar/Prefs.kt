package com.svaronam.diecastradar

import android.content.Context

object Prefs {
    private fun sp(c: Context) = c.getSharedPreferences("radar", Context.MODE_PRIVATE)

    /** URL del servidor en la Pi, p. ej. http://homelab2:8791 (sin barra final). */
    fun server(c: Context): String = (sp(c).getString("server", "") ?: "").trim().trimEnd('/')

    fun setServer(c: Context, value: String) {
        var v = value.trim().trimEnd('/')
        if (v.isNotEmpty() && !v.startsWith("http")) v = "http://$v"
        // servidor nuevo: empezar desde cero, sin soltar el histórico
        sp(c).edit().putString("server", v).putLong("cursor", -1).apply()
    }

    fun cursor(c: Context): Long = sp(c).getLong("cursor", -1)
    fun setCursor(c: Context, v: Long) = sp(c).edit().putLong("cursor", v).apply()

    fun lastOk(c: Context): Long = sp(c).getLong("last_ok", 0)
    fun setLastOk(c: Context, v: Long) = sp(c).edit().putLong("last_ok", v).apply()
}
