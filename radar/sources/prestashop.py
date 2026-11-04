"""Tiendas PrestaShop 1.7/8 (Overnight y muchas tiendas españolas).

Truco: una página de categoría pedida con 'Accept: application/json' y
'X-Requested-With: XMLHttpRequest' devuelve los productos en JSON. Si la
tienda no lo permite, se parsea el HTML (article.product-miniature).
"""
import re

from bs4 import BeautifulSoup

from ..detect import looks_preorder
from ..models import Item

JSON_HEADERS = {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
}
PRICE_RE = re.compile(r"(\d{1,4}(?:[.\s]\d{3})*(?:[,.]\d{1,2})?)")


def parse_price(s):
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    m = PRICE_RE.search(str(s).replace("\xa0", " "))
    if not m:
        return None
    num = m.group(1).replace(" ", "")
    if "," in num:
        num = num.replace(".", "").replace(",", ".")
    try:
        return float(num)
    except ValueError:
        return None


def _slug_of(url):
    m = re.search(r"/(?:\d+-)?([a-z0-9-]+)/?(?:\?.*)?$", url or "")
    return m.group(1) if m else ""


def _cats(*parts):
    vals = [str(x).strip() for x in parts if x and str(x).strip()]
    return "|" + "|".join(vals) + "|" if vals else ""


def _status(text, available, src):
    if src.preorder or looks_preorder(text):
        return "preorder"
    return "available" if available else "soldout"


def _from_json(p, src, cat_url):
    flags = " ".join(f.get("label", "") for f in (p.get("flags") or {}).values()) if isinstance(p.get("flags"), dict) else ""
    text = " ".join(str(x) for x in [p.get("name", ""), p.get("reference", ""), flags,
                                     p.get("availability_message", ""), p.get("category", ""),
                                     p.get("manufacturer_name", ""), cat_url])
    cover = p.get("cover") or {}
    img = None
    if isinstance(cover, dict):
        img = (cover.get("large") or {}).get("url") or (cover.get("bySize", {}).get("home_default") or {}).get("url")
    avail = p.get("availability") in ("available", "last_remaining_items") or bool(p.get("add_to_cart_url"))
    cat_txt = _cats(p.get("category"), p.get("category_name"), p.get("manufacturer_name"), _slug_of(cat_url))
    return Item(
        key=str(p.get("id_product") or p.get("id")),
        title=(p.get("name") or "").strip(),
        url=p.get("url") or p.get("link") or cat_url,
        image=img,
        price=parse_price(p.get("price_amount", p.get("price"))),
        currency=src.currency,
        sku=p.get("reference") or None,
        status=_status(text, avail, src),
        extra_text=text,
        categories=cat_txt,
    )


def _from_html(html, src, cat_url):
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for art in soup.select("article.product-miniature, .product-miniature, .js-product-miniature"):
        pid = art.get("data-id-product")
        a = None
        for sel in (".product-title a", "h3 a", "h2 a", "a.product-thumbnail"):
            a = art.select_one(sel)
            if a and (a.get("title") or a.get_text(strip=True)):
                break
        if not a or not pid:
            continue
        img_tag = art.select_one("img")
        img = None
        if img_tag:
            img = img_tag.get("data-full-size-image-url") or img_tag.get("data-src") or img_tag.get("src")
        price_tag = art.select_one(".price, .product-price")
        text = art.get_text(" ", strip=True) + " " + cat_url
        avail = not re.search(r"fuera de stock|agotado|out of stock", text, re.I)
        out.append(Item(
            key=str(pid),
            title=(a.get("title") or a.get_text(" ", strip=True)).strip(),
            url=a.get("href") or cat_url,
            image=img,
            price=parse_price(price_tag.get_text() if price_tag else None),
            currency=src.currency,
            status=_status(text, avail, src),
            extra_text=text,
            categories=_cats(_slug_of(cat_url)),
        ))
    return out


def fetch(http, src):
    cats = src.categories or ([src.url] if src.url else [])
    items, seen = [], set()
    for cat_url in cats:
        for page in range(1, src.max_pages + 1):
            r = http.get(cat_url, params={"page": page}, headers=JSON_HEADERS)
            r.raise_for_status()
            data = None
            try:
                data = r.json()
            except ValueError:
                pass
            if isinstance(data, dict) and "products" in data:
                parsed = [_from_json(p, src, cat_url) for p in data["products"]]
                pages_count = int((data.get("pagination") or {}).get("pages_count") or page)
            else:
                parsed = _from_html(r.text, src, cat_url)
                pages_count = page + 1 if len(parsed) >= 12 else page
            by_key = {it.key: it for it in items}
            for it in parsed:   # mismo artículo en otra categoría: sumar sus categorías
                old = by_key.get(it.key)
                if old and it.categories and it.categories not in (old.categories or ""):
                    old.categories = (old.categories or "|").rstrip("|") + it.categories
            new = [it for it in parsed if it.key not in seen]
            for it in new:
                seen.add(it.key)
            items.extend(new)
            if not new or page >= pages_count:
                break
    return items
