package com.svaronam.diecastradar

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/** Arranca la escucha al encender el móvil o al actualizar la app. */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (Prefs.server(context).isNotEmpty()) {
            try {
                RadarService.start(context)
            } catch (_: Exception) {
                // algunos fabricantes bloquean arrancar al inicio: se arrancará al abrir la app
            }
        }
    }
}
