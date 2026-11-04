# Diecast Radar 🏁

Bot para la Raspberry que vigila lanzamientos y preorders de coches 1:64 y te avisa al móvil.

- **Webs oficiales:** Tarmac Works, Kaido House, Mattel Creations (RLC), Mini GT y Pop Race.
- **Tiendas españolas:** Overnight y Hot Wheels Spain, cada una con su pestaña. Coches de Metal viene desactivada hasta que la pruebes.
- **Avisos en tu propia APK:** la app Android escucha a la Pi por Tailscale. No pasa nada por Telegram ni por servicios de fuera. Cada aviso trae foto, precio y botones para abrir la ficha o el panel. De noche se guardan y llegan al acabar las horas de silencio.
- **Instagram:** sigue cuentas oficiales, de novedades y de tiendas, y te avisa cuando un post, reel o historia parece un anuncio (preorder, fecha de salida, "coming soon", referencias…). Usa tu bot de Instagram como librería.
- **Panel web:** pensado para el móvil, se abre por Tailscale en `http://homelab2:8791`. Se puede filtrar por marca, estado y texto, y tiene un botón "Revisar ahora".

## Cómo lee cada web (sin navegador, ligero para la Pi 3)

| Plataforma | Webs | Método |
|---|---|---|
| Shopify | Tarmac, Kaido House, Mattel Creations | `/products.json` (JSON público) |
| PrestaShop | Overnight | categoría pedida como JSON (si no, HTML) |
| WooCommerce | Hot Wheels Spain | Store API `/wp-json/wc/store/v1/products` |
| Web propia | Mini GT | HTML de productos y noticias, por código MGT/KHMG |
| `auto` | webs que añadas desde el panel | prueba Shopify y WooCommerce sola |

La **primera pasada** de cada fuente guarda todo lo que ya existe **sin avisar**. A partir de ahí solo te llega lo nuevo:
- **NUEVO**: aparece un modelo que no estaba.
- **PREORDER ABIERTO**: un modelo pasa a estar en preorder.
- **REPUESTO**: un modelo agotado vuelve a estar disponible.

## Instalación en homelab2

```bash
# desde el PC (o clona/copias la carpeta como prefieras)
scp -r diecast-radar usuario@homelab2:~/
ssh usuario@homelab2
cd ~/diecast-radar && bash install.sh
.venv/bin/python -m radar check  # mira qué encuentra cada fuente, sin guardar
sudo systemctl start diecast-radar
journalctl -u diecast-radar -f
```

## App Android propia (los avisos llegan aquí)

En la carpeta `android/` está la APK **Diecast Radar**. No usa Telegram, ni ntfy, ni los servidores de Google: la app habla directamente con la Pi por Tailscale.

- **Cómo recibe los avisos:** un servicio se queda escuchando a la Pi. La Pi le contesta en cuanto aparece un aviso, o a los 50 s si no hay nada, y la app vuelve a preguntar. Así el aviso llega en segundos.
- **Cómo se ven:** con la foto del coche en grande, marca, tipo de aviso, estado, precio y tienda, y botones **Abrir** (la ficha de la tienda) y **Panel**. Los RLC van en un canal aparte, para que les pongas otro sonido.
- **Dentro de la app:** al abrirla se ve el panel. En el menú están *Probar aviso*, *Dirección de la Pi*, *Batería sin restricciones* y *Ajustes de avisos*.
- **Arranque:** se pone en marcha sola al encender el móvil. Si el móvil estuvo sin cobertura, al volver recibe lo que se perdió.
- **Horas de silencio:** las aplica la Pi (`quiet_hours`). Los avisos esperan y llegan cuando acaban.

### Compilarla (GitHub Actions, como Wallabot)

1. Sube esta carpeta a un repo nuevo, por ejemplo `github.com/svaronam/diecast-radar`.
2. El workflow `.github/workflows/apk.yml` compila en cada push que toque `android/`, o a mano desde *Actions → Run workflow*.
3. Descarga el artefacto **DiecastRadar-apk** e instala `DiecastRadar.apk`.

La APK se firma siempre con la misma clave (guardada en GitHub Secrets, ver «Firma de la APK»), así que las versiones nuevas se instalan encima sin desinstalar la anterior.

### Primera vez en el móvil

1. Ten Tailscale activo.
2. Abre la app y pon `http://homelab2:8791`. Si no resuelve el nombre, usa la IP 100.x de homelab2.
3. Acepta las notificaciones y lo de la batería sin restricciones. Sin eso, Android puede dormir la conexión.
4. Menú → **Probar aviso**.

Si algún día prefieres otros canales, Telegram y ntfy siguen disponibles y desactivados en `config.yaml`. Para el servidor ntfy: `INSTALL_NTFY=1 bash install.sh`.

## Instagram

Esta parte no reimplementa Instagram: **importa el `bot.py` de tu panel de Instagram** (`panel-completo`) y usa su sesión (`cookies.json`) de una cuenta de Instagram propia. Si actualizas el panel (por ejemplo, unos `doc_ids` nuevos), esto también se actualiza.

- **Qué lee:** en cada ronda (cada 90 min por defecto) revisa los últimos 12 posts y reels de cada cuenta, más sus historias. Deja una pausa de 15–40 s entre cuentas y va en un hilo aparte, así que no retrasa a las tiendas.
- **Qué considera anuncio:** lo decide por el pie de foto y el texto de la imagen. Cuentan las palabras de preorder o reserva, "coming soon", "drop" o "release", las fechas y horas, los precios y las referencias MGT, KHMG, T64 o PR64. Descarta sorteos, felicitaciones y throwbacks. Solo se guardan y avisan los anuncios.
- **Historias:** lee el texto de la imagen con OCR (tesseract, lo instala `install.sh`). Si la historia tiene un enlace a una tienda, el aviso lleva directo a ella.
- **Sin avisos de golpe:** al añadir una cuenta, lo que ya tenía publicado se guarda sin avisar. Los posts fijados o de hace más de 72 h tampoco avisan.
- **Sesión propia:** abajo del todo de la pestaña *📸 Instagram* hay un apartado *🔑 Sesión de Instagram*: pega `sessionid`, `csrftoken` y `ds_user_id` (vale JSON, `sessionid=…; csrftoken=…` o una por línea). Se comprueban contra Instagram, se guardan en `data/instagram_session.json` (permisos 600) y nunca se muestran. Si no hay sesión propia, usa la del panel de Instagram (`options.account`).
- **Solo las cuentas que sigues:** por defecto la lista sale de a quién sigue la cuenta de la sesión (se sincroniza al guardar la sesión, con el botón *Sincronizar seguidos* y en cada ronda). Para añadir o quitar, sigue o deja de seguir desde la app de Instagram. Hay un interruptor para volver a la lista manual.
- **Gestión desde el panel:** en modo manual puedes añadir (con @nombre o enlace) o quitar cuentas; en los dos modos puedes pausarlas. Las que no existen salen marcadas y se saltan. El chip *📸 Instagram* filtra solo esos anuncios.
- **Fotos:** se guardan en la Pi (`data/media/ig`, se borran a los 30 días), porque los enlaces de Instagram caducan.

Comprobar las cuentas con la sesión: `python -m radar ig-check`.

**En la Pi**, el bot de Instagram tiene que estar en la misma Pi. Ajusta `options.bot_dir` en `config.yaml`; por defecto es `../panel-completo/panel`, relativo a esta carpeta.

**Riesgo:** la cuenta y la IP son las mismas que usa el bot de Instagram. Son unas 2–3 peticiones por cuenta y ronda; si Instagram limita (429), esta parte espera a la siguiente ronda sin insistir.

## Ajustes útiles (`config.yaml`)

- `filters.include`: solo te avisa de lo que contenga esas palabras, por ejemplo `["skyline", "rwb", "porsche"]`. Lo demás se guarda igualmente y se ve en el panel.
- `only_preorder: true` (por tienda): solo avisa de preorders, no de stock normal.
- `every_minutes`: cada cuánto se revisa cada fuente. RLC está a 20 min porque se agotan rápido.
- Para añadir otra tienda, copia un bloque de `sources` y prueba con `python -m radar check --source "nombre"`.

## Lo que hay que comprobar el primer día

- **Pop Race:** se lee de su tienda `shop.poprace.net`. Si en el panel sale *error*, es que la tienda no responde desde tu conexión; los preorders de Pop Race te siguen llegando por Overnight.
- **Mini GT:** su web no es Shopify, así que el lector es el más frágil. Si `check` no saca modelos, avísame y lo ajusto con el HTML real.
- **Mattel Creations:** tiene protección anti-bots. Con `curl_cffi` instalado suele funcionar. Si el panel muestra *error* en esa fuente, prueba a quitar `collection:`. Si te sale mejor otra región, cambia la URL (por ejemplo `https://uk.creations.mattel.com`).

## Comandos

```
python -m radar run          # servicio (lo usa systemd)
python -m radar once         # una pasada y sale
python -m radar check        # prueba fuentes sin guardar ni avisar
python -m radar test-notify  # aviso de prueba (llega a la APK)
python -m radar ig-check     # comprueba las cuentas de Instagram
```

La API está en `/api/items`, `/api/sources` y `/api/events` (este último es el que usa la APK). Sirve si algún día quieres enchufarlo a la app de monitor o a Wallabot.

## Firma de la APK

La clave de firma no está en el repositorio. GitHub Actions la recibe de dos secretos del repo (*Settings → Secrets and variables → Actions*):

| Secreto | Contenido |
|---|---|
| `KEYSTORE_BASE64` | el archivo de la clave en Base64 (`base64 -w0 archivo`) |
| `KEYSTORE_PASSWORD` | su contraseña |

Para compilar en local, deja el archivo de la clave en `android/app/radar.keystore` (está en `.gitignore`) y define `KEYSTORE_PASSWORD` antes de lanzar Gradle.
