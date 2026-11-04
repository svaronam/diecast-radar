"""Envío de avisos: Telegram y/o ntfy. Respeta horas de silencio."""
import datetime as dt
import html
import logging
import time
from zoneinfo import ZoneInfo

import requests

from .detect import brand_label

log = logging.getLogger(__name__)

KIND_LABEL = {
    "new": "NUEVO",
    "preorder_open": "PREORDER ABIERTO",
    "restock": "REPUESTO",
    "test": "PRUEBA",
}
STATUS_LABEL = {
    "preorder": "Preorder",
    "available": "En stock",
    "soldout": "Agotado",
    "announced": "Anunciado",
    "news": "Noticia",
    "unknown": "?",
}


def fmt_price(price, currency):
    if price is None:
        return ""
    sym = {"EUR": "€", "USD": "$", "GBP": "£", "HKD": "HK$"}.get(currency or "", currency or "")
    txt = f"{price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{txt} {sym}" if sym == "€" else f"{sym}{txt}"


def in_quiet_hours(spec: str, tz: str) -> bool:
    if not spec:
        return False
    try:
        a, b = spec.split("-")
        start = dt.time.fromisoformat(a.strip())
        end = dt.time.fromisoformat(b.strip())
    except ValueError:
        log.warning("quiet_hours mal escrito: %s (usa HH:MM-HH:MM)", spec)
        return False
    now = dt.datetime.now(ZoneInfo(tz)).time()
    return (start <= now < end) if start < end else (now >= start or now < end)


class Notifier:
    def __init__(self, cfg: dict, tz: str):
        self.cfg = cfg or {}
        self.tz = tz
        tg = self.cfg.get("telegram") or {}
        self.tg_on = tg.get("enabled") and tg.get("token") and tg.get("chat_id")
        self.tg_token, self.tg_chat = tg.get("token"), str(tg.get("chat_id", ""))
        nt = self.cfg.get("ntfy") or {}
        self.ntfy_on = nt.get("enabled") and nt.get("topic")
        self.ntfy_server = (nt.get("server") or "http://127.0.0.1:2586").rstrip("/")
        self.ntfy_topic = str(nt.get("topic", ""))
        self.ntfy_token = nt.get("token")
        self.max_individual = int(self.cfg.get("max_individual", 8))
        self.panel_url = self.cfg.get("panel_url", "")

    @property
    def enabled(self):
        return bool(self.tg_on or self.ntfy_on)

    # ---------- canales ----------
    def _telegram(self, text, photo=None):
        base = f"https://api.telegram.org/bot{self.tg_token}"
        if photo:
            r = requests.post(base + "/sendPhoto", timeout=20, data={
                "chat_id": self.tg_chat, "photo": photo, "caption": text[:1020], "parse_mode": "HTML"})
            if r.ok:
                return
            log.info("sendPhoto falló (%s), envío solo texto", r.status_code)
        r = requests.post(base + "/sendMessage", timeout=20, data={
            "chat_id": self.tg_chat, "text": text[:4000], "parse_mode": "HTML",
            "disable_web_page_preview": "true"})
        r.raise_for_status()

    def _ntfy(self, title, body, click=None, image=None, tags="racing_car", priority=3, actions=None):
        """Publica en ntfy en JSON (admite emojis y acentos sin problemas)."""
        payload = {"topic": self.ntfy_topic, "title": title, "message": body,
                   "tags": [tags], "priority": priority}
        if click:
            payload["click"] = click
        if image:
            payload["attach"] = image          # el móvil descarga la foto y la muestra en grande
        if actions:
            payload["actions"] = actions
        headers = {"Authorization": f"Bearer {self.ntfy_token}"} if self.ntfy_token else {}
        r = requests.post(self.ntfy_server, json=payload, headers=headers, timeout=20)
        r.raise_for_status()

    # ---------- mensajes ----------
    def _abs(self, url):
        if url and url.startswith("/") and self.panel_url:
            return self.panel_url.rstrip("/") + url
        return url if (url or "").startswith("http") else None

    def send_item(self, ev):
        ev = dict(ev, image=self._abs(ev.get("image")))
        kind = KIND_LABEL.get(ev["kind"], ev["kind"].upper())
        status = STATUS_LABEL.get(ev["status"], ev["status"])
        price = fmt_price(ev["price"], ev["currency"])
        lines = [
            f"{brand_label(ev['brand'])} · <b>{kind}</b>",
            f"<b>{html.escape(ev['title'])}</b>",
            " · ".join(x for x in [status, price, html.escape(ev["source"])] if x),
        ]
        if ev.get("sku"):
            lines.append(f"Ref: <code>{html.escape(ev['sku'])}</code>")
        lines.append(f'<a href="{html.escape(ev["url"])}">Abrir</a>')
        if self.tg_on:
            self._telegram("\n".join(lines), photo=ev.get("image"))
        if self.ntfy_on:
            plain = f"{ev['title']}\n" + " · ".join(x for x in [status, price, ev["source"]] if x)
            if ev.get("sku"):
                plain += f"\nRef: {ev['sku']}"
            actions = [{"action": "view", "label": "Abrir", "url": ev["url"]}]
            if self.panel_url:
                actions.append({"action": "view", "label": "Panel", "url": self.panel_url})
            prio = 4 if ev["kind"] == "preorder_open" or ev["brand"] == "rlc" else 3
            self._ntfy(f"{brand_label(ev['brand'])} · {kind}", plain, click=ev["url"],
                       image=ev.get("image"), priority=prio, actions=actions)

    def send_digest(self, events):
        head = f"🚗 <b>{len(events)} novedades 1:64</b>"
        rows = []
        for ev in events[:30]:
            price = fmt_price(ev["price"], ev["currency"])
            rows.append(f'• {brand_label(ev["brand"]).split(" ")[0]} <a href="{html.escape(ev["url"])}">'
                        f'{html.escape(ev["title"][:70])}</a> {price} <i>({html.escape(ev["source"])})</i>')
        if len(events) > 30:
            rows.append(f"…y {len(events) - 30} más")
        if self.panel_url:
            rows.append(f'\n<a href="{self.panel_url}">Ver todo en el panel</a>')
        if self.tg_on:
            self._telegram(head + "\n" + "\n".join(rows))
        if self.ntfy_on:
            self._ntfy(f"{len(events)} novedades 1:64",
                       "\n".join(f"{e['title']} ({e['source']})" for e in events[:15]),
                       click=self.panel_url or None)

    def test(self):
        msg = "✅ Diecast Radar conectado. Te avisaré de lanzamientos y preorders 1:64."
        if self.tg_on:
            self._telegram(msg)
        if self.ntfy_on:
            self._ntfy("Diecast Radar", msg)

    # ---------- cola ----------
    def flush(self, db):
        if not self.enabled:
            return 0
        if in_quiet_hours(self.cfg.get("quiet_hours", ""), self.tz):
            return 0
        events = db.pending_events()
        if not events:
            return 0
        if len(events) > self.max_individual:
            try:
                self.send_digest(events)
                db.mark_sent([e["event_id"] for e in events], value=2)
            except Exception as e:
                log.error("Error enviando resumen: %s", e)
            return len(events)
        sent = 0
        for ev in events:
            try:
                self.send_item(ev)
                db.mark_sent([ev["event_id"]])
                sent += 1
                time.sleep(1.2)  # límite de Telegram
            except Exception as e:
                log.error("Error enviando aviso (%s): %s", ev["title"], e)
                break  # se reintenta en la próxima vuelta
        return sent
