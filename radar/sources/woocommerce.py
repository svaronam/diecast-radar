"""Tiendas WooCommerce (AG Toy Cars, HobbyXS...) vía la Store API pública:
/wp-json/wc/store/v1/products  → JSON sin claves ni login.
"""
import html

from ..detect import looks_preorder
from ..models import Item


def _price(p):
    pr = p.get("prices") or {}
    raw = pr.get("price")
    if raw in (None, ""):
        return None
    try:
        return int(raw) / (10 ** int(pr.get("currency_minor_unit", 2)))
    except (TypeError, ValueError):
        return None


def fetch(http, src):
    base = src.url.rstrip("/")
    endpoint = base + "/wp-json/wc/store/v1/products"
    queries = src.searches or [""]
    items, seen = [], set()
    for q in queries:
        for page in range(1, src.max_pages + 1):
            params = {"per_page": 100, "page": page, "orderby": "date", "order": "desc"}
            if q:
                params["search"] = q
            if src.categories:
                params["category"] = ",".join(str(c) for c in src.categories)
            data = http.json(endpoint, params=params)
            if not isinstance(data, list) or not data:
                break
            for p in data:
                pid = str(p.get("id"))
                if pid in seen:
                    continue
                seen.add(pid)
                cats = " ".join(c.get("name", "") for c in p.get("categories") or [])
                stock_txt = (p.get("stock_availability") or {}).get("text", "")
                name = html.unescape(p.get("name", "")).strip()
                text = " ".join([name, cats, stock_txt, p.get("sku", ""),
                                 html.unescape(p.get("short_description", ""))[:300]])
                if src.preorder or looks_preorder(text):
                    status = "preorder"
                elif p.get("is_in_stock"):
                    status = "available"
                else:
                    status = "soldout"
                cat_txt = "|" + "|".join(x for c in (p.get("categories") or [])
                                         for x in (c.get("slug"), html.unescape(c.get("name", ""))) if x) + "|"
                imgs = p.get("images") or []
                items.append(Item(
                    key=pid,
                    title=name,
                    url=p.get("permalink") or base,
                    image=imgs[0].get("src") if imgs else None,
                    price=_price(p),
                    currency=(p.get("prices") or {}).get("currency_code") or src.currency,
                    sku=p.get("sku") or None,
                    status=status,
                    extra_text=text,
                    categories=cat_txt if len(cat_txt) > 2 else "",
                ))
            if len(data) < 100:
                break
    return items
