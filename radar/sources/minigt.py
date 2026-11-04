"""Web oficial de Mini GT (minigt.tsm-models.com).

No es Shopify: es una web PHP propia. Se leen las páginas de productos y de
noticias y se extraen los modelos por su código (MGT01234, KHMG123...).
Es la fuente más frágil: si cambian la web, revisa este fichero.
"""
import re
from urllib.parse import urljoin, urlparse, parse_qs

from bs4 import BeautifulSoup

from ..models import Item

BASE = "https://minigt.tsm-models.com/"
DEFAULT_PAGES = [
    BASE + "index.php?action=product",
    BASE + "index.php?action=news",
    BASE,
]
CODE_RE = re.compile(r"\b(MGTS?\d{4,5}|KHMG\d{3,4})(?:-[A-Z]{1,3})?\b")


def _img_near(tag, base):
    img = tag.find("img")
    if img is None and tag.parent is not None:
        img = tag.parent.find("img")
    if img is None:
        return None
    src = img.get("data-src") or img.get("src")
    return urljoin(base, src) if src else None


def _container(a):
    """El bloque 'tarjeta' que contiene el enlace (sube hasta 4 niveles)."""
    node = a
    for _ in range(4):
        if node.parent is None:
            break
        node = node.parent
        if node.name in ("li", "article") or (node.name == "div" and len(node.get_text(strip=True)) > 15):
            return node
    return a


def fetch(http, src):
    pages = src.pages or DEFAULT_PAGES
    items, seen = [], set()
    for page_url in pages:
        html = http.text(page_url)
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            href = urljoin(page_url, a["href"])
            if urlparse(href).netloc and "tsm-models.com" not in urlparse(href).netloc:
                continue
            qs = parse_qs(urlparse(href).query)
            action = (qs.get("action") or [""])[0]
            box = _container(a)
            box_text = box.get_text(" ", strip=True)
            title = (a.get("title") or a.get_text(" ", strip=True) or "").strip()

            if "news" in action and qs.get("id"):
                key = "news-" + qs["id"][0]
                if key in seen or len(title) < 6:
                    continue
                seen.add(key)
                items.append(Item(key=key, title=f"📰 {title}", url=href, image=_img_near(box, page_url),
                                  status="news", extra_text=box_text))
                continue

            if "product" not in action:
                continue
            m = CODE_RE.search(title) or CODE_RE.search(box_text)
            if not m and not qs.get("id"):
                continue
            key = m.group(1) if m else "id-" + qs["id"][0]
            if key in seen:
                continue
            if len(title) < 6:  # enlace de imagen: usa el texto del bloque
                title = box_text[:140]
            if not title:
                continue
            seen.add(key)
            items.append(Item(key=key, title=title, url=href, image=_img_near(box, page_url),
                              sku=m.group(0) if m else None, status="announced",
                              currency="USD", extra_text=box_text))
    return items
