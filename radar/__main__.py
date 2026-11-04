"""Diecast Radar

  python -m radar run                 # servicio: revisa fuentes + panel web + avisos
  python -m radar once [--source X]   # una pasada y sale (útil para probar)
  python -m radar check [--source X]  # prueba fuentes SIN guardar ni avisar: muestra lo que encuentra
  python -m radar test-notify         # manda un mensaje de prueba
  python -m radar ig-check            # comprueba que existen las cuentas de Instagram
"""
import argparse
import logging
import os
import random
import sys
import threading
import time

import yaml

from .core import Filters, run_source
from .db import DB
from .detect import brand_label
from .http import Http
from .models import Source
from .notify import Notifier, fmt_price

log = logging.getLogger("radar")


def load_config(path):
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    # secretos también por variables de entorno
    tg = cfg.setdefault("notify", {}).setdefault("telegram", {})
    tg["token"] = os.environ.get("RADAR_TELEGRAM_TOKEN", tg.get("token"))
    tg["chat_id"] = os.environ.get("RADAR_TELEGRAM_CHAT_ID", tg.get("chat_id"))
    return cfg


def build_sources(cfg, only=None, cfg_path="config.yaml"):
    base = os.path.dirname(os.path.abspath(cfg_path))
    data = os.path.dirname(os.path.abspath(cfg.get("db_path", "data/radar.db")))
    srcs = [Source.from_dict(d) for d in cfg.get("sources", [])]
    for s in srcs:
        s.options.setdefault("_base", base)
        s.options.setdefault("_data", data)
    from . import custom
    names = {s.name for s in srcs}
    for d in custom.load(custom.path_for(cfg)):
        if d.get("name") and d["name"] not in names:
            s = Source.from_dict(d)
            s.options.update(_base=base, _data=data, _custom=True)
            srcs.append(s)
    srcs = [s for s in srcs if s.enabled]
    if only:
        srcs = [s for s in srcs if only.lower() in s.name.lower()]
    return srcs


def one_pass(db, http, srcs, filters, dry=False):
    for src in srcs:
        if dry and src.platform == "instagram":
            print(f"  [{src.name}] en modo prueba no se lee (gastaría peticiones): usa 'python -m radar ig-check'")
            continue
        try:
            platform, items, n = run_source(db, http, src, filters, dry=dry)
            log.info("[%s] %s: %d artículos, %d avisos nuevos", src.name, platform, len(items), n)
            if dry:
                for it in items[:25]:
                    print(f"  {brand_label(it.brand):18} {it.status:9} {fmt_price(it.price, it.currency):>10}  {it.title[:80]}")
                if len(items) > 25:
                    print(f"  … y {len(items) - 25} más")
        except Exception as e:
            log.error("[%s] falló: %s", src.name, e)
            if not dry:
                db.source_status(src.name, ok=False, error=str(e)[:300])


def serve(cfg, db, http, srcs, filters, notifier):
    # Instagram tarda minutos por ronda (pausas entre cuentas): va en su propio hilo
    # para no retrasar a las tiendas.
    slow = [s for s in srcs if s.platform == "instagram"]
    next_run = {s.name: 0.0 for s in srcs}
    wake = threading.Event()
    slow_wake = threading.Event()

    def fast_list():
        return [s for s in list(srcs) if s.platform != "instagram" and s.enabled]

    def add_source(src):
        srcs.append(src)
        next_run[src.name] = 0.0
        wake.set()

    def remove_source(name):
        srcs[:] = [s for s in srcs if s.name != name]
        next_run.pop(name, None)

    def test_source(src):
        from . import sources as _sources
        return _sources.fetch(http, src, None)

    def run_now(include_slow=False):
        for s in fast_list() + (slow if include_slow else []):
            next_run[s.name] = 0.0
        wake.set()
        slow_wake.set()

    def schedule(s):
        jitter = random.uniform(-0.1, 0.1) * s.every_minutes * 60
        next_run[s.name] = time.time() + s.every_minutes * 60 + jitter

    def loop():
        while True:
            now = time.time()
            due = [s for s in fast_list() if now >= next_run.get(s.name, 0.0)]
            if due:
                one_pass(db, http, due, filters)
                for s in due:
                    schedule(s)
            try:
                n = notifier.flush(db)
                if n:
                    log.info("Enviados %d avisos", n)
            except Exception as e:
                log.error("Error en avisos: %s", e)
            wake.wait(30)
            wake.clear()

    def slow_loop():
        time.sleep(20)  # que arranque antes el resto
        while True:
            now = time.time()
            for s in slow:
                if now >= next_run[s.name]:
                    one_pass(db, http, [s], filters)
                    schedule(s)
                    err = (db.sources().get(s.name) or {}).get("last_error") or ""
                    if "limita" in err.lower():  # Instagram frenó: reintentar pronto, no a las 90 min
                        next_run[s.name] = time.time() + 25 * 60
                        log.info("[%s] límite de Instagram: reintento en 25 min", s.name)
            slow_wake.wait(60)
            slow_wake.clear()

    threading.Thread(target=loop, daemon=True, name="scheduler").start()
    if slow:
        threading.Thread(target=slow_loop, daemon=True, name="instagram").start()

    web = cfg.get("web") or {}
    if web.get("enabled", True):
        from waitress import serve as wserve
        from .web import create_app
        app = create_app(db, cfg, srcs, run_now,
                         hooks={"add": add_source, "remove": remove_source, "test": test_source})
        host, port = web.get("host", "0.0.0.0"), int(web.get("port", 8791))
        log.info("Panel web en http://%s:%s", host, port)
        wserve(app, host=host, port=port, threads=8)
    else:
        while True:
            time.sleep(3600)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="radar", description="Avisos de lanzamientos diecast 1:64")
    ap.add_argument("cmd", choices=["run", "once", "check", "test-notify", "ig-check"])
    ap.add_argument("-c", "--config", default=os.environ.get("RADAR_CONFIG", "config.yaml"))
    ap.add_argument("--source", help="solo fuentes cuyo nombre contenga este texto")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    cfg = load_config(a.config)
    db = DB(cfg.get("db_path", "data/radar.db"))
    http = Http(timeout=int(cfg.get("timeout", 25)))
    log.info("HTTP: %s", http.backend)
    srcs = build_sources(cfg, a.source, a.config)
    filters = Filters(cfg.get("filters") or {})
    notifier = Notifier(cfg.get("notify") or {}, cfg.get("timezone", "Europe/Madrid"))

    if a.cmd == "test-notify":
        if not notifier.enabled:
            rows = db.list_items(limit=1)
            if not rows:
                sys.exit("Aún no hay artículos guardados: ejecuta antes 'python -m radar once'")
            db.add_event(rows[0]["uid"], "test")
            print("Aviso de prueba en cola: la APK lo mostrará en unos segundos.")
            return
        notifier.test()
        print("Mensaje de prueba enviado.")
    elif a.cmd == "ig-check":
        from .sources import instagram
        igs = [s for s in build_sources(cfg, None, a.config) if s.platform == "instagram"]
        if not igs:
            sys.exit("No hay ninguna fuente de Instagram activa en config.yaml")
        print("Comprobando cuentas (con pausas para no levantar sospechas)...")
        for user, ok, info in instagram.check_accounts(igs[0]):
            print(f"  {'✔' if ok == 'ok' else '✘'} @{user:24} {info}")
    elif a.cmd == "check":
        one_pass(db, http, srcs, filters, dry=True)
    elif a.cmd == "once":
        one_pass(db, http, srcs, filters)
        print(f"Avisos enviados: {notifier.flush(db)}")
    else:
        if not notifier.enabled:
            log.info("Avisos: los recoge la APK por /api/events (Telegram/ntfy desactivados)")
        serve(cfg, db, http, srcs, filters, notifier)


if __name__ == "__main__":
    main()
