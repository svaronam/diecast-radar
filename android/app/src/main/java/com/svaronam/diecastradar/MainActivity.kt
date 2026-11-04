package com.svaronam.diecastradar

import android.Manifest
import android.annotation.SuppressLint
import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Bundle
import android.os.PowerManager
import android.provider.Settings
import android.text.InputType
import android.view.Menu
import android.view.MenuItem
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.Toast
import kotlin.concurrent.thread

/** Pantalla principal: el panel web de la Pi + ajustes. */
class MainActivity : Activity() {

    private lateinit var web: WebView

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        Notifs.ensureChannels(this)

        web = WebView(this)
        web.settings.javaScriptEnabled = true
        web.settings.domStorageEnabled = true
        web.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, req: WebResourceRequest): Boolean {
                val url = req.url.toString()
                val server = Prefs.server(this@MainActivity)
                if (server.isNotEmpty() && url.startsWith(server)) return false
                // fichas de tiendas: al navegador
                startActivity(Intent(Intent.ACTION_VIEW, req.url))
                return true
            }

            override fun onReceivedError(view: WebView, req: WebResourceRequest, err: WebResourceError) {
                if (req.isForMainFrame) showOffline(err.description?.toString() ?: "")
            }
        }
        setContentView(FrameLayout(this).apply { addView(web) })

        askNotificationPermission()
        if (Prefs.server(this).isEmpty()) askServer(first = true) else start()
    }

    override fun onResume() {
        super.onResume()
        if (Prefs.server(this).isNotEmpty()) RadarService.start(this)
    }

    private fun start() {
        RadarService.start(this)
        web.loadUrl(Prefs.server(this))
    }

    private fun showOffline(detail: String) {
        val html = """
            <html><body style="font-family:sans-serif;padding:24px;background:#121315;color:#eee">
            <h2>No llego a la Pi</h2>
            <p>Comprueba que <b>Tailscale</b> está activo en el móvil y que el servicio corre en la Raspberry.</p>
            <p style="color:#999">${Prefs.server(this)}<br>$detail</p>
            <p><a style="color:#ff7a5c" href="${Prefs.server(this)}">Reintentar</a></p>
            </body></html>""".trimIndent()
        web.loadDataWithBaseURL(null, html, "text/html", "utf-8", null)
    }

    private fun askNotificationPermission() {
        if (checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 1)
        }
    }

    private fun askServer(first: Boolean = false) {
        val input = EditText(this).apply {
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
            setText(Prefs.server(this@MainActivity).ifEmpty { "http://homelab2:8791" })
            setSelection(text.length)
        }
        val box = FrameLayout(this).apply {
            setPadding(60, 20, 60, 0)
            addView(input)
        }
        AlertDialog.Builder(this)
            .setTitle("Dirección de la Pi")
            .setMessage("Con Tailscale activo. Si no resuelve el nombre, usa la IP 100.x.x.x de homelab2.")
            .setView(box)
            .setCancelable(!first)
            .setPositiveButton("Guardar") { _, _ ->
                Prefs.setServer(this, input.text.toString())
                RadarService.start(this, reconnect = true)
                web.loadUrl(Prefs.server(this))
                if (first) askBattery()
            }
            .show()
    }

    @SuppressLint("BatteryLife")
    private fun askBattery() {
        val pm = getSystemService(PowerManager::class.java)
        if (!pm.isIgnoringBatteryOptimizations(packageName)) {
            AlertDialog.Builder(this)
                .setTitle("Que no se duerma")
                .setMessage("Para que los avisos lleguen al momento con la pantalla apagada, permite que la app funcione sin restricciones de batería.")
                .setPositiveButton("Permitir") { _, _ ->
                    try {
                        startActivity(Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
                            Uri.parse("package:$packageName")))
                    } catch (_: Exception) {
                        startActivity(Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS))
                    }
                }
                .setNegativeButton("Ahora no", null)
                .show()
        } else {
            Toast.makeText(this, "La batería ya está sin restricciones", Toast.LENGTH_SHORT).show()
        }
    }

    private fun testNotification() {
        val server = Prefs.server(this)
        thread {
            val msg = try {
                Api.post("$server/api/test-event")
                "Aviso de prueba enviado: llegará en unos segundos"
            } catch (e: Exception) {
                "No se pudo: ${e.message?.take(120)}"
            }
            runOnUiThread { Toast.makeText(this, msg, Toast.LENGTH_LONG).show() }
        }
    }

    override fun onCreateOptionsMenu(menu: Menu): Boolean {
        menu.add(0, 1, 0, "Recargar")
        menu.add(0, 2, 1, "Probar aviso")
        menu.add(0, 3, 2, "Dirección de la Pi")
        menu.add(0, 4, 3, "Batería sin restricciones")
        menu.add(0, 5, 4, "Ajustes de avisos")
        return true
    }

    override fun onOptionsItemSelected(item: MenuItem): Boolean {
        when (item.itemId) {
            1 -> web.loadUrl(Prefs.server(this))
            2 -> testNotification()
            3 -> askServer()
            4 -> askBattery()
            5 -> startActivity(Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS)
                .putExtra(Settings.EXTRA_APP_PACKAGE, packageName))
            else -> return super.onOptionsItemSelected(item)
        }
        return true
    }

    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        if (web.canGoBack()) web.goBack() else super.onBackPressed()
    }
}
