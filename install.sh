#!/usr/bin/env bash
# Instala Diecast Radar como servicio en la Raspberry (Raspberry Pi OS Lite 64-bit).
# Uso:  cd ~/diecast-radar && bash install.sh
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_USER="${SUDO_USER:-$USER}"

echo "==> Paquetes del sistema"
sudo apt-get update -qq
sudo apt-get install -y -qq python3-venv python3-pip
# OCR para leer el texto de las historias de Instagram
sudo apt-get install -y -qq tesseract-ocr tesseract-ocr-eng tesseract-ocr-spa || echo "   (sin OCR: las historias se juzgarán por sus enlaces)"

echo "==> Entorno virtual"
python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install -q --upgrade pip
# curl_cffi es opcional: si no compila en la Pi, seguimos sin él
"$APP_DIR/.venv/bin/pip" install -q requests beautifulsoup4 PyYAML flask waitress
"$APP_DIR/.venv/bin/pip" install -q curl_cffi || echo "   (curl_cffi no disponible, se usará requests)"

if [ ! -f "$APP_DIR/config.yaml" ]; then
  cp "$APP_DIR/config.example.yaml" "$APP_DIR/config.yaml"
  echo "==> Creado config.yaml (revisa las fuentes si quieres)"
fi
mkdir -p "$APP_DIR/data"

if [ "${INSTALL_NTFY:-0}" = "1" ]; then
  echo "==> Servidor de avisos ntfy (propio, solo en tu red/Tailscale)"
  if ! command -v ntfy >/dev/null 2>&1; then
    sudo apt-get install -y -qq curl gpg
    sudo mkdir -p /etc/apt/keyrings
    curl -fsSL https://archive.heckel.io/apt/pubkey.txt | sudo gpg --dearmor --yes -o /etc/apt/keyrings/archive.heckel.io.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/archive.heckel.io.gpg] https://archive.heckel.io/apt debian main" \
      | sudo tee /etc/apt/sources.list.d/archive.heckel.io.list >/dev/null
    sudo apt-get update -qq
    sudo apt-get install -y -qq ntfy
  fi
  sudo tee /etc/ntfy/server.yml >/dev/null <<EOF
# ntfy de homelab: lo escucha el móvil por Tailscale
base-url: "http://$(hostname):2586"
listen-http: ":2586"
cache-file: "/var/cache/ntfy/cache.db"
cache-duration: "72h"        # si el móvil estuvo sin conexión, recibe lo pendiente
behind-proxy: false
EOF
  sudo mkdir -p /var/cache/ntfy && sudo chown -R ntfy:ntfy /var/cache/ntfy 2>/dev/null || true
  sudo systemctl enable --now ntfy >/dev/null
  sudo systemctl restart ntfy
fi

echo "==> Servicio systemd"
sudo tee /etc/systemd/system/diecast-radar.service >/dev/null <<EOF
[Unit]
Description=Diecast Radar (avisos lanzamientos 1:64)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$APP_USER
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/.venv/bin/python -m radar run -c $APP_DIR/config.yaml
Restart=on-failure
RestartSec=30
Environment=PYTHONUNBUFFERED=1
# Pi 3: que no se coma la RAM si algo va mal
MemoryMax=300M
Nice=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable diecast-radar >/dev/null

cat <<MSG

Listo. Siguientes pasos:
  1) .venv/bin/python -m radar check       # prueba las fuentes sin guardar nada
  2) sudo systemctl start diecast-radar
  3) En el móvil (Tailscale activo): abre la APK Diecast Radar y pon http://$(hostname):8791
  4) En la APK: menú -> "Probar aviso"
  (el panel también se abre en el navegador: http://$(hostname):8791)
Logs: journalctl -u diecast-radar -f
MSG
