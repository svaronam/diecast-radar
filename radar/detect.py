"""Detección de marca, estado (preorder...) y filtros por palabras clave."""
import re

BRANDS = {
    "kaido":   {"name": "Kaido House",    "emoji": "🏮", "patterns": [r"kaido", r"\bKHMG\d"]},
    "tarmac":  {"name": "Tarmac Works",   "emoji": "🏁", "patterns": [r"tarmac", r"\bT64[GRSP]?-"]},
    "poprace": {"name": "Pop Race",       "emoji": "🟨", "patterns": [r"pop\s?race", r"\bPR64\d", r"\bPRE\d{3}\b", r"\bPRDC-?\d"]},
    "rlc":     {"name": "Hot Wheels RLC / Elite 64", "emoji": "🔴",
                "patterns": [r"red\s?line\s?club", r"\bRLC\b", r"elite\s?64"]},
    "minigt":  {"name": "Mini GT",        "emoji": "🟥", "patterns": [r"mini[\s-]?gt", r"\bMGTS?\d{3}"]},
}
# Orden importa: Kaido House va antes que Mini GT (sus coches llevan "x Mini GT").
ORDER = ["kaido", "tarmac", "poprace", "rlc", "minigt"]

_BRAND_RE = {k: [re.compile(p, re.I) for p in v["patterns"]] for k, v in BRANDS.items()}

PREORDER_RE = re.compile(
    r"pre[\s-]?orders?|preventa|pre-venta|pre-?pedido|reserva|pr[oó]ximamente|"
    r"coming\s+soon|llegada\s+inminente|en\s+camino",
    re.I,
)

# Escalas que no son 1:64 -> fuera por defecto
OTHER_SCALES_RE = re.compile(r"\b1\s?[/:]\s?(12|18|24|32|43|87)\b")


def detect_brand(text: str):
    for key in ORDER:
        if any(rx.search(text) for rx in _BRAND_RE[key]):
            return key
    return None


def looks_preorder(text: str) -> bool:
    return bool(PREORDER_RE.search(text or ""))


def compile_list(patterns):
    return [re.compile(p, re.I) for p in (patterns or [])]


def matches_any(rx_list, text: str) -> bool:
    return any(rx.search(text) for rx in rx_list)


def brand_label(key) -> str:
    b = BRANDS.get(key or "")
    return f"{b['emoji']} {b['name']}" if b else "🚗 Otra marca"
