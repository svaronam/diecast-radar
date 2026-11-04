package com.svaronam.diecastradar

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.drawable.Icon
import android.net.Uri
import org.json.JSONObject

object Notifs {
    const val CH_ALERTS = "avisos"
    const val CH_RLC = "rlc"
    const val CH_SERVICE = "servicio"
    const val SERVICE_ID = 1
    private const val GROUP = "radar"
    private const val ACCENT = 0xFFD4351C.toInt()

    private fun nm(c: Context) = c.getSystemService(NotificationManager::class.java)

    fun ensureChannels(c: Context) {
        val nm = nm(c)
        nm.createNotificationChannel(NotificationChannel(
            CH_ALERTS, "Lanzamientos y preorders", NotificationManager.IMPORTANCE_HIGH).apply {
            description = "Modelos nuevos, preorders abiertos y reposiciones"
        })
        nm.createNotificationChannel(NotificationChannel(
            CH_RLC, "Hot Wheels RLC", NotificationManager.IMPORTANCE_HIGH).apply {
            description = "Drops del Red Line Club (se agotan en minutos)"
        })
        nm.createNotificationChannel(NotificationChannel(
            CH_SERVICE, "Conexión con la Pi", NotificationManager.IMPORTANCE_MIN).apply {
            description = "Aviso fijo mientras la app escucha a la Raspberry"
            setShowBadge(false)
        })
    }

    private fun openApp(c: Context): PendingIntent =
        PendingIntent.getActivity(c, 0, Intent(c, MainActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)

    private fun openUrl(c: Context, url: String, req: Int): PendingIntent {
        val i = if (url.startsWith("http")) Intent(Intent.ACTION_VIEW, Uri.parse(url))
        else Intent(c, MainActivity::class.java)
        i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        return PendingIntent.getActivity(c, req, i,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
    }

    fun service(c: Context, text: String): Notification =
        Notification.Builder(c, CH_SERVICE)
            .setSmallIcon(R.drawable.ic_stat_car)
            .setContentTitle("Diecast Radar")
            .setContentText(text)
            .setOngoing(true)
            .setColor(ACCENT)
            .setContentIntent(openApp(c))
            .build()

    fun updateService(c: Context, text: String) {
        nm(c).notify(SERVICE_ID, service(c, text))
    }

    fun item(c: Context, e: JSONObject) {
        val id = e.optInt("event_id")
        var model = e.optString("title")
        var page = e.optString("source")
        // Instagram: "@cuenta · texto" -> página "Instagram · @cuenta"
        Regex("^(@[\\w.]+) · (.*)$", RegexOption.DOT_MATCHES_ALL).find(model)?.let {
            page = "$page · ${it.groupValues[1]}"
            model = it.groupValues[2]
        }
        model = model.replace(Regex("^[\\s\\-–]*(pre-?order|preventa)[\\s\\-–:]*", RegexOption.IGNORE_CASE), "")
            .removePrefix("📰").trim()
        val brand = e.optString("brand_label").ifBlank { "Otras marcas" }
        val status = e.optString("status_label").ifBlank { "Novedad" }
        val url = e.optString("url")
        val channel = if (e.optString("brand") == "rlc") CH_RLC else CH_ALERTS
        // imágenes guardadas en la Pi (Instagram) llegan como /media/...: se piden a la Pi
        val rawImg = e.optString("image").let { if (it.startsWith("/")) Prefs.server(c) + it else it }
        val img = rawImg.takeIf { it.startsWith("http") }?.let { Api.bitmap(it) }
        val summary = "$brand · $status\n$page"

        val b = Notification.Builder(c, channel)
            .setSmallIcon(R.drawable.ic_stat_car)
            .setColor(ACCENT)
            .setContentTitle(model)
            .setContentText("$brand · $status")
            .setSubText(page)
            .setAutoCancel(true)
            .setGroup(GROUP)
            .setShowWhen(true)
            .setWhen(e.optLong("created", System.currentTimeMillis() / 1000) * 1000)
            .setContentIntent(openUrl(c, url, 10_000 + id))
            .addAction(Notification.Action.Builder(null as Icon?, "Abrir", openUrl(c, url, 20_000 + id)).build())
            .addAction(Notification.Action.Builder(null as Icon?, "Panel", openApp(c)).build())

        if (img != null) {
            b.setLargeIcon(img)
                .setStyle(Notification.BigPictureStyle()
                    .bigPicture(img)
                    .bigLargeIcon(null as Bitmap?)
                    .setBigContentTitle(model)
                    .setSummaryText(summary))
        } else {
            b.setStyle(Notification.BigTextStyle().setBigContentTitle(model).bigText(summary))
        }
        nm(c).notify(1000 + id, b.build())
    }

    /** Si llegan muchos de golpe: un solo aviso con la lista. */
    fun digest(c: Context, events: List<JSONObject>) {
        val style = Notification.InboxStyle()
            .setBigContentTitle("${events.size} novedades 1:64")
        events.take(7).forEach {
            style.addLine("${it.optString("brand_label").take(2)} ${it.optString("title")} · ${it.optString("source")}")
        }
        if (events.size > 7) style.setSummaryText("y ${events.size - 7} más en el panel")
        val n = Notification.Builder(c, CH_ALERTS)
            .setSmallIcon(R.drawable.ic_stat_car)
            .setColor(ACCENT)
            .setContentTitle("${events.size} novedades 1:64")
            .setContentText("Toca para verlas en el panel")
            .setStyle(style)
            .setAutoCancel(true)
            .setContentIntent(openApp(c))
            .build()
        nm(c).notify(900_000 + (events.last().optInt("event_id") % 1000), n)
    }
}
