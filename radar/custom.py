"""Webs añadidas desde el panel (se guardan en data/custom_sources.json)."""
import json
import os
import re
import threading
from urllib.parse import urlparse

_lock = threading.Lock()


def path_for(cfg):
    return os.path.join(os.path.dirname(os.path.abspath(cfg.get("db_path", "data/radar.db"))),
                        "custom_sources.json")


def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def save(path, items):
    with _lock:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=1)
        os.replace(tmp, path)


def from_url(url, name=None, brand=None, currency="EUR", only_preorder=False):
    """Convierte una URL pegada en la definición de una fuente. Reconoce enlaces de
    colección de Shopify y de categoría de PrestaShop; el resto lo detecta sola."""
    url = (url or "").strip()
    if not url:
        raise ValueError("Pega la dirección de la web")
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    u = urlparse(url)
    if not u.netloc or "." not in u.netloc:
        raise ValueError("La dirección no parece válida")
    base = f"{u.scheme}://{u.netloc}"
    host = u.netloc.lower().removeprefix("www.")
    d = {"name": (name or "").strip() or host, "platform": "auto", "url": base, "kind": "retailer",
         "currency": currency or "EUR", "every_minutes": 60, "enabled": True,
         "default_brand": brand or None, "only_preorder": bool(only_preorder)}
    m = re.search(r"/collections/([^/?#]+)", u.path)
    if m:
        d.update(platform="shopify", collection=m.group(1))
    elif re.search(r"/\d+-[\w-]+/?$", u.path):
        d.update(platform="prestashop", categories=[url.split("#")[0]])
    return d
