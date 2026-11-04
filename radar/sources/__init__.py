"""Adaptadores por plataforma. Todos devuelven list[Item]."""
import logging

from . import shopify, prestashop, woocommerce, minigt, instagram

log = logging.getLogger(__name__)

ADAPTERS = {
    "shopify": shopify.fetch,
    "prestashop": prestashop.fetch,
    "woocommerce": woocommerce.fetch,
    "minigt": minigt.fetch,
    "instagram": instagram.fetch,
}


def detect_platform(http, src):
    """Prueba qué plataforma usa una web (para platform: auto)."""
    base = src.url.rstrip("/")
    probes = [
        ("shopify", base + "/products.json?limit=1", lambda j: "products" in j),
        ("woocommerce", base + "/wp-json/wc/store/v1/products?per_page=1", lambda j: isinstance(j, list)),
    ]
    for name, url, ok in probes:
        try:
            r = http.get(url, retries=0)
            if r.status_code == 200 and ok(r.json()):
                return name
        except Exception:
            pass
    if src.categories:
        return "prestashop"
    raise RuntimeError("No reconozco la plataforma de la web; indícala en el config (platform: ...)")


def fetch(http, src, db=None):
    platform = src.platform
    if platform == "auto":
        platform = (db.get_platform(src.name) if db else None) or detect_platform(http, src)
    fn = ADAPTERS.get(platform)
    if not fn:
        raise ValueError(f"Plataforma desconocida: {platform}")
    return platform, fn(http, src)
