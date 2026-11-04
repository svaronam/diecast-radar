"""Tiendas Shopify (Tarmac Works, Kaido House, Mattel Creations, Miskha Garage...).

Shopify expone /products.json (o /collections/<handle>/products.json) con todos
los productos en JSON: no hace falta navegador ni parsear HTML.
"""
from ..detect import looks_preorder
from ..models import Item


def _status(text, available, src):
    if src.preorder or looks_preorder(text):
        return "preorder"
    return "available" if available else "soldout"


def fetch(http, src):
    base = src.url.rstrip("/")
    path = f"/collections/{src.collection}/products.json" if src.collection else "/products.json"
    items, seen = [], set()
    for page in range(1, src.max_pages + 1):
        data = http.json(base + path, params={"limit": 250, "page": page})
        products = data.get("products", [])
        # los más nuevos primero (así en el panel quedan arriba aunque se guarden de golpe)
        ordered = sorted(products, key=lambda x: x.get("published_at") or x.get("created_at") or "", reverse=True)
        for p in ordered:
            pid = str(p.get("id"))
            if pid in seen:
                continue
            seen.add(pid)
            variants = p.get("variants") or [{}]
            v0 = variants[0]
            available = any(v.get("available") for v in variants)
            tags = p.get("tags") or []
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(",")]
            text = " ".join([p.get("title", ""), p.get("vendor", ""), p.get("product_type", ""), " ".join(tags)])
            images = p.get("images") or []
            try:
                price = float(v0.get("price")) if v0.get("price") is not None else None
            except (TypeError, ValueError):
                price = None
            items.append(Item(
                key=pid,
                title=p.get("title", "").strip(),
                url=f"{base}/products/{p.get('handle')}",
                image=images[0].get("src") if images else None,
                price=price,
                currency=src.currency,
                sku=v0.get("sku") or None,
                status=_status(text, available, src),
                extra_text=text,
            ))
        if len(products) < 250:
            break
    return items
