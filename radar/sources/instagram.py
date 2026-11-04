"""Instagram: anuncios de lanzamientos en posts, reels e historias de cuentas de diecast.

No reimplementa Instagram: importa el bot.py de tu panel de Instagram (panel-completo)
y usa su clase `Instagram` con la sesión guardada en su cookies.json. Así, si el panel
se actualiza (doc_ids, cambios de Instagram), esto también.

Por cada cuenta:   perfil (solo la 1ª vez, para el id) → últimos 12 posts → historias.
Cada post/historia nuevo se clasifica (pie de foto + OCR de la imagen) y solo los que
parecen anuncio (preorder, fecha, "coming soon", referencias...) se guardan y avisan.
"""
import importlib.util
import json
import logging
import os
import random
import re
import threading
import time
from urllib.parse import urlparse

import requests

from .. import igtext, ocr
from ..detect import detect_brand
from ..models import Item

log = logging.getLogger(__name__)

_lock = threading.Lock()
_bot = {}          # bot_dir -> módulo bot.py importado
_clients = {}      # (bot_dir, cuenta) -> (cliente, creado)
CLIENT_TTL = 6 * 3600
FOLLOWING_TTL = 6 * 3600   # cada cuánto se relee a quién sigue la sesión
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36")
CODE_RE = re.compile(r"\b(MGTS?\d{4,5}|KHMG\d{3}|T64[GRSP]?-[\w-]+|PR64\d{4}|PRE\d{3})\b", re.I)


# ------------------------------------------------------------------ rutas y estado
def _paths(src):
    data = src.options.get("_data") or "data"
    return {
        "accounts": os.path.join(data, "instagram.json"),
        "state": os.path.join(data, "instagram_state.json"),
        "session": os.path.join(data, "instagram_session.json"),
        "media": os.path.join(data, "media", "ig"),
    }


def _load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def _norm_account(a):
    if isinstance(a, str):
        a = {"user": a}
    user = str(a.get("user", "")).strip().lstrip("@").lower()
    m = re.search(r"instagram\.com/([\w.]+)", user)
    if m:
        user = m.group(1)
    return {"user": user, "brand": a.get("brand"), "kind": a.get("kind", "news"),
            "enabled": a.get("enabled", True)}


def _acc_data(src):
    p = _paths(src)["accounts"]
    with _lock:
        data = _load(p, None)
        if data is None:
            data = {"accounts": [_norm_account(a) for a in src.accounts]}
            _save(p, data)
    return data


def accounts(src):
    """Cuentas a seguir. Se guardan en data/instagram.json (editable desde el panel);
    la primera vez se copian del config.yaml."""
    data = _acc_data(src)
    return [_norm_account(a) for a in data.get("accounts", []) if _norm_account(a)["user"]]


def save_accounts(src, accs, **extra):
    with _lock:
        p = _paths(src)["accounts"]
        data = _load(p, {}) or {}
        data["accounts"] = [_norm_account(a) for a in accs]
        data.update(extra)
        _save(p, data)


def mode(src):
    """'following' (por defecto): solo las cuentas que sigue la sesión · 'manual': la lista a mano."""
    return _acc_data(src).get("mode", "following")


def following_at(src):
    return _acc_data(src).get("following_at")


def state(src):
    return _load(_paths(src)["state"], {"accounts": {}})


# ------------------------------------------------------------------ sesión propia (cookies pegadas en el panel)
_COOKIE_KEYS = ("sessionid", "csrftoken", "ds_user_id")
_COOKIE_RE = re.compile(r"(sessionid|csrftoken|ds_user_id)[\"']?\s*[=:\t ]\s*[\"']?([^;\s\"',}]+)", re.I)


def parse_cookies(raw):
    """Acepta JSON (objeto o lista de Cookie-Editor), 'k=v; k=v' o líneas 'nombre valor'."""
    raw = (raw or "").strip()
    found = {}
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            data = data.get("cookies", data)
        if isinstance(data, dict):
            found = {k: str(v) for k, v in data.items() if k in _COOKIE_KEYS}
        elif isinstance(data, list):
            found = {c["name"]: str(c["value"]) for c in data
                     if isinstance(c, dict) and c.get("name") in _COOKIE_KEYS}
    except (ValueError, KeyError, TypeError):
        pass
    if not found:
        for k, v in _COOKIE_RE.findall(raw):
            found.setdefault(k.lower(), v)
    if not found.get("sessionid"):
        # sin nombres: valores sueltos (uno por línea, o separados por espacios, comas o ;)
        for tok in re.split(r"[\s;,]+", raw.replace('"', " ").replace("'", " ")):
            if re.match(r"^\d{5,}(?:%3A|:)[\w%:\-.]{15,}$", tok):
                found["sessionid"] = tok
            elif re.match(r"^[A-Za-z0-9]{32}$", tok):
                found.setdefault("csrftoken", tok)
            elif re.match(r"^\d{5,}$", tok):
                found.setdefault("ds_user_id", tok)
    if found.get("sessionid") and not found.get("ds_user_id"):
        m = re.match(r"(\d+)(?:%3A|:)", found["sessionid"])
        if m:
            found["ds_user_id"] = m.group(1)
    return found


def session_info(src):
    s = _load(_paths(src)["session"], None)
    if s and s.get("cookies", {}).get("sessionid"):
        return {"user": s.get("user"), "saved": s.get("saved")}
    return None


def session_save(src, raw):
    """Valida las cookies contra Instagram y las guarda. Devuelve el @ de la sesión."""
    cookies = parse_cookies(raw)
    if not cookies.get("sessionid"):
        raise ValueError(f"No encuentro la cookie sessionid en lo que has pegado ({len(raw.strip())} caracteres). "
                         "Pega el valor de sessionid (empieza por un número, p. ej. 123456789%3A…), "
                         "solo o con su nombre: sessionid=…; csrftoken=…")
    bot = load_bot(src)
    try:
        ig = bot.Instagram(cookies)
        user = ig.yo()
    except bot.SesionCaducada as e:
        raise ValueError(f"Instagram no acepta esa sesión: {e}") from e
    except bot.SinAcceso as e:
        raise ValueError(f"Instagram no acepta esa sesión: {e}") from e
    except bot.Limitado as e:
        raise ValueError(f"Instagram está limitando las peticiones ({e}). Prueba en unos minutos.") from e
    except bot.RespuestaRara as e:
        raise ValueError(f"Respuesta rara de Instagram: {e}") from e
    path = _paths(src)["session"]
    with _lock:
        _save(path, {"user": user, "cookies": cookies, "saved": int(time.time())})
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        _clients.clear()
    return user


def session_clear(src):
    with _lock:
        try:
            os.remove(_paths(src)["session"])
        except OSError:
            pass
        _clients.clear()


_BRAND_GUESS = [("kaido", r"kaido"), ("tarmac", r"tarmac"), ("poprace", r"pop_?race"),
                ("minigt", r"mini_?gt"), ("rlc", r"hotwheels|hot_wheels|mattel|redline|\brlc")]
_SHOP_RE = re.compile(r"shop|store|tienda|toys?|models?|hobby|overnight|miniatur|cars|garage|coleccion", re.I)


def guess_account(user):
    for brand, rx in _BRAND_GUESS:
        if re.search(rx, user, re.I):
            return {"user": user, "brand": brand, "kind": "official"}
    return {"user": user, "brand": None, "kind": "shop" if _SHOP_RE.search(user) else "news"}


def fetch_following(ig):
    """Usuarios que sigue la cuenta de la sesión (paginado)."""
    uid = ig.mi_id
    if not uid:
        raise RuntimeError("falta ds_user_id en las cookies")
    users, max_id = [], None
    for _ in range(20):
        params = {"count": 200}
        if max_id:
            params["max_id"] = max_id
        d = ig.get(f"/api/v1/friendships/{uid}/following/", **params)
        users += [{"user": str(u["username"]).lower(), "pk": str(u.get("pk") or u.get("id") or ""),
                   "private": bool(u.get("is_private"))} for u in d.get("users", []) if u.get("username")]
        max_id = d.get("next_max_id")
        if not max_id:
            break
        _pause(2, 4)
    seen, out = set(), []
    for u in users:
        if u["user"] not in seen:
            seen.add(u["user"])
            out.append(u)
    return out


def sync_following(src, ig):
    """Deja la lista de cuentas = las que sigue la sesión (conserva marca/tipo/pausa de las conocidas).
    La lista de seguidos ya trae el id de cada cuenta: así no hace falta consultar cada perfil
    (esa consulta es la que más rápido limita Instagram)."""
    users = fetch_following(ig)
    old = {a["user"]: a for a in accounts(src)}
    accs = [old[u["user"]] if u["user"] in old else guess_account(u["user"]) for u in users]
    save_accounts(src, accs, following_at=int(time.time()))
    path = _paths(src)["state"]
    with _lock:
        st = _load(path, {"accounts": {}})
        for u in users:
            if u["pk"]:
                a = st.setdefault("accounts", {}).setdefault(u["user"], {})
                a.update(uid=u["pk"], private=u["private"])
                a.pop("missing", None)
        _save(path, st)
    log.info("[Instagram] sigues a %d cuentas", len(accs))
    return accs


# ------------------------------------------------------------------ puente con bot.py
def _bot_dir(src):
    """Carpeta del bot.py del panel. Si la ruta del config no vale (p. ej. el zip se
    descomprimió dentro de otra carpeta), lo busca subiendo carpetas."""
    base = os.path.abspath(src.options.get("_base") or ".")
    d = src.options.get("bot_dir") or "../panel-completo/panel"
    if not os.path.isabs(d):
        d = os.path.normpath(os.path.join(base, d))
    if os.path.exists(os.path.join(d, "bot.py")):
        return d
    cur = base
    for _ in range(4):
        for cand in ("panel-completo/panel", "panel", "panel-completo"):
            p = os.path.normpath(os.path.join(cur, cand))
            if os.path.exists(os.path.join(p, "bot.py")) and os.path.exists(os.path.join(p, "web.py")):
                log.info("[Instagram] bot de Instagram encontrado en %s", p)
                return p
        cur = os.path.dirname(cur)
    return d


def load_bot(src):
    d = _bot_dir(src)
    if d in _bot:
        return _bot[d]
    path = os.path.join(d, "bot.py")
    if not os.path.exists(path):
        raise RuntimeError(f"No encuentro el bot de Instagram en {path} (instagram.bot_dir en config.yaml)")
    spec = importlib.util.spec_from_file_location("igbot_panel", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.log = lambda msg: log.info("[ig] %s", str(msg).strip())   # que no escriba en el log del panel
    _bot[d] = mod
    return mod


def client(src, fresh=False):
    bot = load_bot(src)
    own = _load(_paths(src)["session"], None)
    if own and own.get("cookies", {}).get("sessionid"):
        key = (_bot_dir(src), "own", own.get("saved"))
    else:
        own, key = None, (_bot_dir(src), src.options.get("account"))
    cached = _clients.get(key)
    if cached and not fresh and time.time() - cached[1] < CLIENT_TTL:
        return bot, cached[0]
    if own:
        ig = bot.Instagram(own["cookies"])
        try:
            usuario = ig.yo()
        except bot.SinAcceso as e:
            raise bot.SesionCaducada(str(e))
        ig.usuario = usuario
    else:
        ig, usuario = bot.cliente(None, src.options.get("account") or None)
    log.info("[Instagram] sesión de @%s lista", usuario)
    _clients[key] = (ig, time.time())
    return bot, ig


# ------------------------------------------------------------------ utilidades de items de IG
def caption_of(it):
    c = it.get("caption")
    if isinstance(c, dict):
        return c.get("text") or ""
    if isinstance(c, str):
        return c
    edges = ((it.get("edge_media_to_caption") or {}).get("edges")) or []
    return (edges[0].get("node") or {}).get("text", "") if edges else ""


def image_url(it):
    """Mejor imagen del item (la portada si es vídeo, la 1ª si es carrusel)."""
    media = (it.get("carousel_media") or [it])[0]
    cands = ((media.get("image_versions2") or {}).get("candidates")) or []
    if cands:
        return max(cands, key=lambda c: (c.get("width") or 0) * (c.get("height") or 0)).get("url")
    return media.get("display_url") or it.get("display_url")


def story_links(it):
    urls = []
    for st in it.get("story_link_stickers") or []:
        u = (st.get("story_link") or {}).get("url")
        if u:
            urls.append(u)
    for cta in it.get("story_cta") or []:
        for l in cta.get("links") or []:
            if l.get("webUri"):
                urls.append(l["webUri"])
    clean = []
    for u in urls:  # Instagram envuelve los enlaces en l.instagram.com/?u=...
        m = re.search(r"[?&]u=([^&]+)", u)
        if "l.instagram.com" in u and m:
            from urllib.parse import unquote
            u = unquote(m.group(1))
        clean.append(u)
    return clean


def download(url, path):
    if not url:
        return False
    if os.path.exists(path):
        return True
    try:
        r = requests.get(url, timeout=30, headers={"User-Agent": UA, "Referer": "https://www.instagram.com/"})
        if r.status_code != 200 or len(r.content) < 1000:
            return False
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(r.content)
        return True
    except requests.RequestException:
        return False


def clean_media(media_dir, days=30):
    limit = time.time() - days * 86400
    try:
        for name in os.listdir(media_dir):
            p = os.path.join(media_dir, name)
            if os.path.getmtime(p) < limit:
                os.remove(p)
    except OSError:
        pass


def _pause(a, b):
    time.sleep(random.uniform(a, b))


# ------------------------------------------------------------------ ficha de la cuenta
class Missing(Exception):
    pass


def resolve(bot, ig, user):
    """id y privacidad de la cuenta. Primero la API de ficha (ligera y dice claramente
    si no existe); si falla, el método del bot (cargar la página del perfil)."""
    try:
        d = ig.get("/api/v1/users/web_profile_info/", username=user)
        u = (d.get("data") or {}).get("user")
        if not u:
            raise Missing("el perfil no existe")
        return {"id": str(u.get("id") or u.get("pk")), "privado": bool(u.get("is_private")),
                "media_count": (u.get("edge_owner_to_timeline_media") or {}).get("count")}
    except bot.SinAcceso as e:
        if "no encontrado" in str(e) or "404" in str(e):
            raise Missing("el perfil no existe") from e
    except (bot.RespuestaRara, ValueError, KeyError):
        pass
    try:
        return ig.perfil(user)
    except bot.SinAcceso as e:
        if "no existe" in str(e):
            raise Missing(str(e)) from e
        raise
    except bot.RespuestaRara as e:
        # la web devuelve su página de error (httpErrorPage) para perfiles que no existen
        dbg = os.path.join(getattr(bot, "BASE", "."), "debug_perfil.html")
        try:
            with open(dbg, encoding="utf-8", errors="ignore") as f:
                if '"httpErrorPage"' in f.read():
                    raise Missing("el perfil no existe (o no está disponible)") from e
        except OSError:
            pass
        raise


# ------------------------------------------------------------------ una cuenta
def _build_item(acc, kind, key, text, analysis, url, img_path, silent):
    brand = detect_brand(text) or acc.get("brand")
    head = igtext.headline(text) or ("nueva historia" if kind == "story" else "nuevo post")
    m = CODE_RE.search(text)
    label = "historia" if kind == "story" else ("reel" if kind == "reel" else "post")
    return Item(
        key=key,
        title=f"@{acc['user']} · {head}",
        url=url,
        image=("/media/ig/" + os.path.basename(img_path)) if img_path else None,
        status=analysis["status"],
        brand=brand,
        sku=m.group(1).upper() if m else None,
        extra_text=f"{label} {text[:800]}",
        silent=silent,
    )


def check_account(src, bot, ig, acc, st, opts, media_dir):
    """Revisa una cuenta. Devuelve la lista de Items (solo anuncios)."""
    user = acc["user"]
    out = []
    first = not st.get("seen_once")
    seen = st.setdefault("seen", [])
    max_age = float(opts.get("max_age_hours", 72)) * 3600
    use_ocr = opts.get("ocr", True) and ocr.available()

    if not st.get("uid"):
        p = resolve(bot, ig, user)
        st.update(uid=p["id"], private=p["privado"])
        _pause(2, 5)
    uid = st["uid"]
    if st.get("private") and not opts.get("follow_private"):
        st["note"] = "cuenta privada"
        return out

    # ---------- posts y reels
    items, _ = ig.posts(uid, 12, username=user)
    for it in items:
        code = it.get("code") or it.get("shortcode")
        if not code or f"p:{code}" in seen:
            continue
        seen.append(f"p:{code}")
        text = caption_of(it)
        a = igtext.analyze(text)
        img_path = os.path.join(media_dir, f"{user}_{code}.jpg")
        if not a["is_ad"] and use_ocr and opts.get("ocr_posts", True) and len(text) < 120:
            if download(image_url(it), img_path):  # pie corto: el anuncio suele ir en la imagen
                text = (text + "\n" + ocr.read_text(img_path)).strip()
                a = igtext.analyze(text)
        if not a["is_ad"]:
            continue
        download(image_url(it), img_path)
        old = time.time() - float(it.get("taken_at") or time.time()) > max_age
        kind = "reel" if it.get("product_type") == "clips" else "post"
        out.append(_build_item(acc, kind, f"post:{code}", text, a,
                               f"https://www.instagram.com/p/{code}/",
                               img_path if os.path.exists(img_path) else None, first or old))

    # ---------- historias
    if opts.get("stories", True):
        _pause(3, 8)
        for it in ig.historias(uid, username=user) or []:
            pk = str(it.get("pk") or it.get("id") or "").split("_")[0]
            if not pk or f"s:{pk}" in seen:
                continue
            seen.append(f"s:{pk}")
            links = story_links(it)
            img_path = os.path.join(media_dir, f"{user}_s{pk}.jpg")
            got = download(image_url(it), img_path)
            text = ocr.read_text(img_path) if (use_ocr and got) else ""
            text = "\n".join([text] + [urlparse(u).netloc + urlparse(u).path for u in links]).strip()
            a = igtext.analyze(text)
            if not use_ocr:  # sin OCR: solo historias de cuentas oficiales con enlace
                a["is_ad"] = a["is_ad"] or (bool(links) and acc.get("kind") == "official")
            if links and a["is_ad"] and a["status"] != "preorder" and "preorder" in links[0].lower():
                a["status"] = "preorder"
            if not a["is_ad"]:
                if got and not opts.get("keep_all_media"):
                    try:
                        os.remove(img_path)
                    except OSError:
                        pass
                continue
            url = links[0] if links else f"https://www.instagram.com/stories/{user}/{pk}/"
            out.append(_build_item(acc, "story", f"story:{pk}", text, a, url,
                                   img_path if got else None, first))
    del seen[:-400]
    return out


# ------------------------------------------------------------------ fuente completa
def fetch(http, src):
    paths = _paths(src)
    opts = src.options
    bot = load_bot(src)
    try:
        _, ig = client(src)
    except bot.SesionCaducada as e:
        raise RuntimeError(f"Instagram: la sesión no vale ({e}). Pega cookies nuevas "
                           "abajo del todo en la pestaña Instagram") from e
    fa = following_at(src)
    if mode(src) == "following" and (not fa or time.time() - fa > FOLLOWING_TTL):
        try:
            sync_following(src, ig)
        except bot.Limitado as e:
            raise RuntimeError(f"Instagram limita las peticiones ({e}); sigo en la próxima ronda") from e
        except Exception as e:
            log.warning("[Instagram] no pude leer a quién sigues (%s): uso la última lista guardada", e)
        _pause(3, 6)
    st_all = state(src)
    sts = st_all.setdefault("accounts", {})
    accs = [a for a in accounts(src) if a.get("enabled", True)]
    out, fatal = [], None
    for i, acc in enumerate(accs):
        st = sts.setdefault(acc["user"], {})
        if st.get("missing"):
            continue
        try:
            found = check_account(src, bot, ig, acc, st, opts, paths["media"])
            out.extend(found)
            st.update(seen_once=True, last_ok=int(time.time()), error=None, last_found=len(found))
            log.info("[Instagram] @%s: %d anuncios", acc["user"], len(found))
        except Missing as e:
            st.update(error=str(e), missing=True)
            log.warning("[Instagram] @%s no existe: la salto (quítala o corrige el nombre en el panel)", acc["user"])
        except bot.SinAcceso as e:
            st["error"] = str(e)
        except bot.Limitado as e:
            st["error"] = f"limitado: {e}"
            fatal = RuntimeError(f"Instagram limita las peticiones ({e}); sigo en la próxima ronda")
        except bot.RespuestaRara as e:  # rareza de esta cuenta: no tumbar la ronda
            st["error"] = str(e)[:200]
            log.warning("[Instagram] @%s: %s", acc["user"], e)
        except bot.SesionCaducada as e:
            _clients.clear()
            st["error"] = str(e)
            fatal = RuntimeError(f"Instagram: sesión caducada ({e})")
        except Exception as e:  # respuesta rara de una cuenta: no tumbar al resto
            st["error"] = str(e)[:200]
            log.warning("[Instagram] @%s: %s", acc["user"], e)
        finally:
            st["last_run"] = int(time.time())
            _save(paths["state"], st_all)
        if fatal:
            break
        if i < len(accs) - 1:
            lo, hi = opts.get("pause_seconds", [15, 40])
            _pause(lo, hi)
    clean_media(paths["media"])
    if fatal and not out:
        raise fatal
    if fatal:
        log.warning(str(fatal))
    return out


def check_accounts(src):
    """Comprueba que existen las cuentas (para `python -m radar ig-check`)."""
    bot = load_bot(src)
    _, ig = client(src)
    res = []
    for acc in accounts(src):
        try:
            p = resolve(bot, ig, acc["user"])
            res.append((acc["user"], "ok", f"{'privada' if p['privado'] else 'pública'} · {p.get('media_count')} posts"))
        except (Missing, bot.SinAcceso, bot.RespuestaRara) as e:
            res.append((acc["user"], "NO", str(e)))
        except bot.Limitado as e:
            res.append((acc["user"], "límite", str(e)))
            break
        _pause(4, 9)
    return res
