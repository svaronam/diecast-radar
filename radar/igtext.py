"""¿Es un anuncio de lanzamiento? Clasifica el texto de un post/historia de Instagram
(pie de foto y/o texto leído de la imagen con OCR)."""
import re

_MONTHS = (r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|"
           r"sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?|"
           r"enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre")

RULES = [
    # (nombre, peso, regex)
    ("preorder", 4, r"pre[\s\-]?orders?|pre[\s\-]?venta|pre[\s\-]?pedidos?|\breserva(?:s|lo|la)?\b|\breservas? abiertas?"),
    ("soon",     2, r"coming soon|pr[oó]ximamente|sneak peek|first look|teaser|prototype|prototipo|"
                    r"new release|upcoming|stay tuned|announc\w*|anuncio|reveal(?:ed)?|novedad(?:es)?|"
                    r"next drop|new casting|nuevo molde"),
    ("live",     2, r"available now|now available|out now|on sale|in stock|re-?stock|ya disponible|"
                    r"disponible(?:s)? (?:ya|en|desde)|\bdrops?\b|dropping|goes live|live now|\balert\b|\blaunch\w*|lanzamiento|\breleas\w*|"
                    r"shop now|link in (?:bio|story)|tap the link|swipe up|enlace en (?:la )?bio|ya a la venta"),
    ("date",     1, rf"\b(?:{_MONTHS})\.?\s+\d{{1,2}}(?:st|nd|rd|th)?\b|\b\d{{1,2}}(?:st|nd|rd|th)?\s+(?:de\s+)?(?:{_MONTHS})\b|"
                    r"\b\d{1,2}[/.]\d{1,2}(?:[/.]\d{2,4})?\b|"
                    r"\b\d{1,2}(?::\d{2})?\s?(?:am|pm|hkt|pst|pdt|est|edt|cet|cest|jst|uhr)\b|"
                    r"\b(?:today|tonight|tomorrow|hoy|mañana|this (?:friday|saturday|sunday|week))\b"),
    ("code",     2, r"\b(?:MGTS?\d{4,5}|KHMG\d{3}|T64[GRSP]?-[\w-]+|PR64\d{4}|PRE\d{3}|PRDC-?\d+)\b"),
    ("price",    1, r"[$€£¥]\s?\d|\d+[.,]\d{2}\s?(?:usd|eur|hkd|€)|\bhk\$|\busd\s?\d|precio|price"),
    ("164",      1, r"\b1\s?[:/]\s?64\b|\b64\s?scale|escala 1/64"),
    ("neg",     -3, r"giveaway|sorteo|happy (?:birthday|holidays|new year|halloween)|merry christmas|"
                    r"feliz navidad|throwback|#tbt|meet\s?up|event recap|thank you for coming|gracias por venir|"
                    r"we(?:'| a)re hiring|job opening"),
]
_COMPILED = [(n, w, re.compile(rx, re.I)) for n, w, rx in RULES]

THRESHOLD = 4

_HASHTAGS_ONLY = re.compile(r"^(?:[#@][\w.]+\s*)+$")
_SPACES = re.compile(r"\s+")


def analyze(text: str):
    """Devuelve dict(score, hits, is_ad, status)."""
    text = text or ""
    hits = {}
    for name, weight, rx in _COMPILED:
        n = len(rx.findall(text))
        if n:  # varias señales del mismo tipo suman (máx. 2)
            hits[name] = weight * (min(n, 2) if weight > 0 else 1)
    score = sum(hits.values())
    is_ad = score >= THRESHOLD or ("preorder" in hits and "neg" not in hits)
    status = "preorder" if "preorder" in hits else "announced"
    return {"score": score, "hits": sorted(hits), "is_ad": is_ad, "status": status}


def headline(text: str, max_len: int = 110) -> str:
    """Primera línea con contenido (sin bloques de hashtags), recortada."""
    for line in (text or "").splitlines():
        line = line.strip(" \t-–—•·|")
        if len(line) < 4 or _HASHTAGS_ONLY.match(line):
            continue
        line = _SPACES.sub(" ", line)
        return line if len(line) <= max_len else line[: max_len - 1].rstrip() + "…"
    return ""
