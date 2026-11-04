"""Una pasada por una fuente: descargar, filtrar, guardar y generar eventos."""
import logging

from . import sources
from .detect import detect_brand, compile_list, matches_any, OTHER_SCALES_RE

log = logging.getLogger(__name__)

ACTIVE = ("preorder", "available", "announced")


class Filters:
    def __init__(self, cfg: dict):
        self.include = compile_list(cfg.get("include"))
        self.exclude = compile_list(cfg.get("exclude"))
        self.only_164 = cfg.get("only_164", True)
        self.brands = set(cfg.get("brands") or [])

    def wants_item(self, it, src) -> bool:
        """¿Guardamos este artículo? (marca, escala, exclusiones)."""
        if src.keep_all:
            return True
        text = f"{it.title} {it.extra_text}"
        allowed = set(src.brands) or self.brands
        if allowed and it.brand not in allowed:
            return False
        if self.only_164 and OTHER_SCALES_RE.search(it.title):
            return False
        if matches_any(self.exclude, it.title) or matches_any(compile_list(src.exclude), text):
            return False
        req = compile_list(src.require)
        if req and not matches_any(req, text):
            return False
        return True

    def alert_scope(self, it, src) -> bool:
        """Con keep_all se guarda todo, pero solo se avisa de tus marcas o de cualquier preorder."""
        if not src.keep_all or src.alert_all:
            return True
        return it.brand in self.brands or it.status == "preorder"

    def wants_alert(self, it) -> bool:
        """¿Avisamos? (palabras clave del usuario)."""
        return not self.include or matches_any(self.include, it.title)


def run_source(db, http, src, filters: Filters, dry=False):
    platform, raw = sources.fetch(http, src, db)
    kept = []
    for it in raw:
        it.source = src.name
        # primero título/referencia; tags y categorías solo si no hay pista mejor
        it.brand = it.brand or (detect_brand(f"{it.title} {it.sku or ''}")
                    or detect_brand(it.extra_text)
                    or src.default_brand)
        if filters.wants_item(it, src):
            kept.append(it)

    if dry:
        return platform, kept, 0

    import time
    now = int(time.time())  # misma hora para toda la pasada: el orden lo decide el id de producto
    seeding = db.count_source(src.name) == 0  # primera vez: guardar sin avisar
    if src.platform == "instagram":
        seeding = False  # Instagram lo controla por cuenta (cuenta nueva = sin avisar)
    n_events = 0
    for it in kept:
        prev = db.get(it.uid)
        if prev is None:
            dup = db.url_seen_elsewhere(it.url, src.name)
            db.insert(it, now)
            if dup or it.silent:
                continue
            if seeding or not filters.wants_alert(it) or not filters.alert_scope(it, src):
                continue
            if src.only_preorder and it.status != "preorder":
                continue
            if it.status == "soldout":
                continue
            db.add_event(it.uid, "new")
            n_events += 1
        else:
            changed = prev["status"] != it.status
            db.update(it, changed, now)
            if not changed or not filters.wants_alert(it) or not filters.alert_scope(it, src):
                continue
            if it.status == "preorder" and prev["status"] != "preorder":
                db.add_event(it.uid, "preorder_open"); n_events += 1
            elif (it.status == "available" and prev["status"] == "soldout"
                  and not src.only_preorder):
                db.add_event(it.uid, "restock"); n_events += 1
    if seeding:
        log.info("[%s] primera pasada: %d artículos guardados sin avisar", src.name, len(kept))
    db.source_status(src.name, ok=True, count=len(kept), platform=platform)
    return platform, kept, n_events
