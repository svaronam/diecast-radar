"""Panel web (móvil) accesible por Tailscale: http://homelab2:8791"""
import datetime as dt
import os
import time
from zoneinfo import ZoneInfo

from flask import Flask, abort, jsonify, redirect, render_template_string, request, send_from_directory, url_for

from .detect import BRANDS, ORDER, brand_label
from .models import Source
from .notify import KIND_LABEL, STATUS_LABEL, fmt_price, in_quiet_hours

PAGE = r"""<!doctype html>
<html lang="es"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Diecast Radar</title>
<style>
:root{--bg:#f4f3ef;--card:#fff;--ink:#17181a;--muted:#6b6e73;--line:#e3e1da;--accent:#d4351c;
--pre:#0b6bcb;--ok:#1d8a4e;--off:#9a9ca0;--chip:#ecebe6}
@media (prefers-color-scheme:dark){:root{--bg:#121315;--card:#1c1d20;--ink:#ececec;--muted:#9a9ca3;
--line:#2c2e33;--chip:#26282c;--pre:#5aa9ff;--ok:#4cc483}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.4 -apple-system,system-ui,"Segoe UI",Roboto,sans-serif}
header{position:sticky;top:0;z-index:5;background:var(--bg);padding:14px 16px 8px;border-bottom:1px solid var(--line)}
h1{font-size:19px;margin:0 0 10px;letter-spacing:-.01em}h1 span{color:var(--accent)}
.row{display:flex;gap:8px;overflow-x:auto;padding-bottom:6px;scrollbar-width:none}
.chip{flex:none;padding:6px 11px;border-radius:999px;background:var(--chip);color:var(--ink);
text-decoration:none;font-size:13px;white-space:nowrap;border:1px solid transparent}
.chip.on{border-color:var(--ink);font-weight:600}
.tabs{display:flex;gap:0;margin:-2px 0 10px;border-bottom:1px solid var(--line);overflow-x:auto;white-space:nowrap;scrollbar-width:none}
.tab{padding:8px 7px;text-decoration:none;color:var(--muted);font-weight:600;font-size:12.5px;border-bottom:2px solid transparent;margin-bottom:-1px}
.tab.on{color:var(--ink);border-bottom-color:var(--accent)}
.panelbox{margin:12px 16px 0;padding:12px;background:var(--card);border:1px solid var(--line);border-radius:14px;font-size:13.5px;color:var(--ink)}
.panelbox h2{font-size:15px;margin:0 0 8px}.panelbox table{width:100%;border-collapse:collapse}
.panelbox td{padding:6px 2px;border-top:1px solid var(--line)}.panelbox p{color:var(--muted)}
form.s{display:flex;gap:8px;margin:6px 0 2px}input[type=search]{flex:1;padding:9px 12px;border-radius:10px;
border:1px solid var(--line);background:var(--card);color:var(--ink);font-size:15px}
button{padding:9px 12px;border-radius:10px;border:0;background:var(--ink);color:var(--bg);font-weight:600}
main{padding:12px 16px 40px;display:grid;gap:10px;grid-template-columns:repeat(auto-fill,minmax(300px,1fr))}
.card{display:flex;gap:12px;background:var(--card);border:1px solid var(--line);border-radius:14px;padding:10px;
text-decoration:none;color:inherit}
.card img,.ph{width:96px;height:72px;object-fit:contain;border-radius:8px;background:var(--chip);flex:none}
.t{font-weight:600;font-size:14px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.meta{color:var(--muted);font-size:12.5px;margin-top:4px}
.st{font-size:11.5px;font-weight:700;text-transform:uppercase;letter-spacing:.03em}
.st.preorder{color:var(--pre)}.st.available{color:var(--ok)}.st.soldout{color:var(--off)}
.st.announced,.st.news{color:var(--accent)}
details{margin:0 16px;padding:10px 0;color:var(--muted);font-size:13px}
details table{width:100%;border-collapse:collapse;margin-top:6px}
details td{padding:4px 2px;border-top:1px solid var(--line)}.err{color:var(--accent)}
.empty{color:var(--muted);padding:30px 0}
.ig td{vertical-align:middle}.ig form{display:inline}.ig input[type=text]{padding:7px 10px;border-radius:9px;
border:1px solid var(--line);background:var(--card);color:var(--ink);font-size:14px;width:150px}
.ig select{padding:7px;border-radius:9px;border:1px solid var(--line);background:var(--card);color:var(--ink)}
.mini{padding:3px 9px;font-size:12px;border-radius:8px}.off{opacity:.45}.okc{color:var(--ok)}
</style></head><body>
<header>
<h1>Diecast <span>Radar</span> · 1:64</h1>
{% if ig_on or sections %}<nav class="tabs">
{% for sc in sections %}<a class="tab {{'on' if tab=='sec:' ~ sc.key}}" href="{{ url_for('section_tab', key=sc.key) }}">{{ sc.label }}</a>{% endfor %}
{% if ig_on %}<a class="tab {{'on' if tab=='ig'}}" href="{{ url_for('instagram_tab') }}">📸 Instagram</a>{% endif %}
<a class="tab {{'on' if tab=='radar'}}" href="{{ url_for('index') }}">🏁 Tiendas</a></nav>{% endif %}
<div class="row">
 <a class="chip {{'on' if not brand}}" href="{{ link(brand=None) }}">Todas</a>
 {% for k in order %}<a class="chip {{'on' if brand==k}}" href="{{ link(brand=k) }}">{{ brands[k].emoji }} {{ brands[k].name }}</a>{% endfor %}
</div>
{% if tab == 'radar' and web_chips|length > 1 %}<div class="row"><span style="color:var(--muted);font-size:12px;align-self:center">Webs</span>
 <a class="chip {{'on' if not sel_web}}" href="{{ link(source=None) }}">Todas</a>
 {% for w in web_chips %}<a class="chip {{'on' if sel_web==w.name}}" href="{{ link(source=w.name) }}">{{ w.name }} <small style="opacity:.6">{{ w.count }}</small></a>{% endfor %}
</div>{% endif %}
{% for g in cat_rows %}<div class="row"><span style="color:var(--muted);font-size:12px;align-self:center">{{ g.title }}</span>
 <a class="chip {{'on' if not cat}}" href="{{ link(cat=None) }}">Todas</a>
 {% for c in g.chips %}<a class="chip {{'on' if cat==c.label}}" href="{{ link(cat=c.label) }}">{{ c.label }} <small style="opacity:.6">{{ c.count }}</small></a>{% endfor %}
</div>{% endfor %}
<div class="row">
  <a class="chip {{'on' if not status}}" href="{{ link(status=None) }}">Cualquier estado</a>
 {% for s in ['preorder','announced','available','soldout','news'] %}
 <a class="chip {{'on' if status==s}}" href="{{ link(status=s) }}">{{ status_label[s] }}</a>{% endfor %}
</div>
<form class="s" method="get">
 {% if brand %}<input type="hidden" name="brand" value="{{brand}}">{% endif %}
 {% if status %}<input type="hidden" name="status" value="{{status}}">{% endif %}
 {% if sel_web and tab == 'radar' %}<input type="hidden" name="source" value="{{sel_web}}">{% endif %}
 {% if cat %}<input type="hidden" name="cat" value="{{cat}}">{% endif %}
 <input type="search" name="q" value="{{ q or '' }}" placeholder="Buscar (Skyline, LBWK, MGT01…)">
 <button>Buscar</button>
</form>
</header>
{% if tab != 'ig' %}<details {{ 'open' if src_msg }}><summary>Fuentes ({{ sources|length }}) · <form method="post" action="{{ url_for('run_now') }}" style="display:inline"><button style="padding:4px 10px;font-size:12px">Revisar ahora</button></form></summary>
{% if src_msg %}<p class="{{ 'err' if src_msg.startswith('⚠') else 'okc' }}" style="margin:8px 12px;font-weight:600">{{ src_msg }}</p>{% endif %}
<table>{% for s in sources %}<tr class="{{ '' if s.enabled else 'off' }}"><td>{{ s.name }}{% if s.custom %} <small>(añadida)</small>{% endif %}</td><td>{{ s.count }}</td>
<td>{% if s.error %}<span class="err" title="{{ s.error }}">error</span>{% else %}{{ s.when }}{% endif %}</td>
<td style="text-align:right;white-space:nowrap">{% if s.custom %}
<form method="post" action="{{ url_for('src_toggle') }}" style="display:inline"><input type="hidden" name="name" value="{{ s.name }}"><button class="mini">{{ 'Pausar' if s.enabled else 'Activar' }}</button></form>
<form method="post" action="{{ url_for('src_remove') }}" style="display:inline" onsubmit="return confirm('¿Quitar {{ s.name }} y sus artículos?')"><input type="hidden" name="name" value="{{ s.name }}"><button class="mini">Quitar</button></form>{% endif %}</td></tr>{% endfor %}</table>
{% if tab == 'radar' %}<form method="post" action="{{ url_for('src_add') }}" style="display:flex;gap:6px;flex-wrap:wrap;margin:10px 12px" onsubmit="var b=this.querySelector('button');b.disabled=true;b.textContent='Probando la web…';">
<input type="text" name="url" placeholder="Dirección de la web o de su sección de preorders" required style="flex:1 1 260px">
<input type="text" name="name" placeholder="Nombre (opcional)" style="flex:1 1 140px">
<select name="brand"><option value="">marca: detectar</option>{% for k in order %}<option value="{{k}}">{{ brands[k].name }}</option>{% endfor %}</select>
<select name="currency"><option>EUR</option><option>USD</option><option>GBP</option><option>HKD</option></select>
<label style="font-size:12px;align-self:center"><input type="checkbox" name="only_preorder" value="1"> solo avisar de preorders</label>
<button class="mini" style="padding:7px 12px">Añadir web</button></form>
<p style="margin:0 12px 10px;font-size:12px;color:var(--muted)">Vale la web (Shopify, WooCommerce) o el enlace de una categoría (Shopify: /collections/…, PrestaShop: /123-nombre). La pruebo antes de guardarla; lo que ya tenga se guarda sin avisar. Solo se guardan las marcas que sigues (Tarmac, Mini GT, Pop Race, Kaido, RLC).</p>{% endif %}
</details>
{% endif %}
{% if tab == 'ig' %}<section class="panelbox ig"><h2>Cuentas ({{ ig_accounts|length }}) · sesión {{ '@' ~ ig_session if ig_session else 'sin sesión' }}
<form method="post" action="{{ url_for('ig_run') }}" style="display:inline"><button class="mini">Revisar ahora</button></form></h2>
{% if ig_msg %}<p class="okc" style="margin:0 0 6px">{{ ig_msg }}</p>{% endif %}
{% if ig_err %}<p class="err" style="margin:0 0 6px">{{ ig_err }}</p>{% endif %}
{% if not ig_session %}<p class="err" style="margin:0 0 6px">Falta la sesión: pega las cookies en el apartado de abajo del todo.</p>{% endif %}
<p style="margin:0 0 8px">Modo:
<form method="post" action="{{ url_for('ig_mode') }}" style="display:inline"><input type="hidden" name="mode" value="{{ 'manual' if ig_mode=='following' else 'following' }}">
<b>{{ 'solo las cuentas que sigue la sesión' if ig_mode=='following' else 'lista manual' }}</b> <button class="mini">Cambiar a {{ 'lista manual' if ig_mode=='following' else 'solo las que sigo' }}</button></form>
{% if ig_mode=='following' %}<form method="post" action="{{ url_for('ig_sync') }}" style="display:inline"><button class="mini">Sincronizar seguidos</button></form>
<small>{{ 'última sincronización ' ~ ig_following_when if ig_following_when else 'aún sin sincronizar' }}</small>{% endif %}</p>
{% if not ig_accounts %}<p>No hay cuentas todavía. {{ 'Sigue cuentas con la cuenta de la sesión y pulsa «Sincronizar seguidos».' if ig_mode=='following' else 'Añade alguna abajo.' }}</p>{% endif %}
<table>{% for a in ig_accounts %}<tr class="{{ '' if a.enabled else 'off' }}">
<td><a href="https://www.instagram.com/{{ a.user }}/" target="_blank" rel="noopener" style="color:inherit">@{{ a.user }}</a>
 <small>{{ brands[a.brand].emoji if a.brand in brands else '' }} {{ 'oficial' if a.kind=='official' else ('tienda' if a.kind=='shop' else 'novedades') }}</small></td>
<td>{% if a.missing %}<span class="err">no existe</span>{% elif a.error %}<span class="err" title="{{ a.error }}">error</span>{% elif a.when %}<span class="okc">✔</span> {{ a.when }}{% else %}pendiente{% endif %}</td>
<td style="text-align:right;white-space:nowrap">
<form method="post" action="{{ url_for('ig_toggle') }}"><input type="hidden" name="user" value="{{ a.user }}"><button class="mini">{{ 'Pausar' if a.enabled else 'Activar' }}</button></form>
{% if ig_mode!='following' %}<form method="post" action="{{ url_for('ig_remove') }}"><input type="hidden" name="user" value="{{ a.user }}"><button class="mini">Quitar</button></form>{% endif %}</td></tr>{% endfor %}</table>
{% if ig_mode=='following' %}<p style="margin:8px 0 0"><small>La lista sale de a quién sigues en Instagram: para añadir o quitar, sigue o deja de seguir desde la app.</small></p>
{% else %}<form method="post" action="{{ url_for('ig_add') }}" style="display:flex;gap:6px;flex-wrap:wrap;margin-top:8px">
<input type="text" name="user" placeholder="@cuenta o enlace" required>
<select name="brand"><option value="">marca: detectar</option>{% for k in order %}<option value="{{k}}">{{ brands[k].name }}</option>{% endfor %}</select>
<select name="kind"><option value="news">novedades</option><option value="official">oficial</option><option value="shop">tienda</option></select>
<button class="mini" style="padding:7px 12px">Añadir</button></form>{% endif %}
<p style="margin:8px 0 0">Se revisan cada {{ ig_every }} min con pausas entre cuentas. Solo avisa de lo que parece un anuncio (preorder, fecha, "coming soon", referencias…).
OCR de historias: {{ 'activo' if ig_ocr else 'no disponible (instala tesseract)' }}.</p>
</section>{% endif %}
<main>
{% for it in items %}
<a class="card" href="{{ it.url }}" target="_blank" rel="noopener">
 {% if it.image %}<img src="{{ it.image }}" loading="lazy" alt="">{% else %}<div class="ph"></div>{% endif %}
 <div><div class="st {{ it.status }}">{{ status_label.get(it.status, it.status) }}</div>
 <div class="t">{{ it.title }}</div>
 <div class="meta">{{ brands[it.brand].emoji if it.brand in brands else '🚗' }} {{ it.source }}{% if it.price_txt %} · {{ it.price_txt }}{% endif %} · {{ it.seen }}</div></div>
</a>
{% else %}<div class="empty">Nada por aquí todavía.</div>{% endfor %}
</main>
{% if tab == 'ig' %}<section class="panelbox ig" id="sesion" style="margin-top:14px"><h2>🔑 Sesión de Instagram</h2>
{% if ig_msg %}<p class="{{ 'err' if ig_msg.startswith('⚠') else 'okc' }}" style="margin:0 0 8px;font-weight:600">{{ ig_msg }}</p>{% endif %}
<p style="margin:0 0 8px">{% if ig_own %}Sesión propia guardada: <b>@{{ ig_session }}</b>{% if ig_session_when %} · {{ ig_session_when }}{% endif %}.
{% elif ig_session %}<b>Aún no has guardado una sesión aquí.</b> Ahora mismo usa la del panel de Instagram (@{{ ig_session }}).
{% else %}Todavía no hay sesión.{% endif %}
Se guarda solo en esta Pi y nunca se muestra aquí.</p>
<form method="post" action="{{ url_for('ig_session') }}" onsubmit="var b=this.querySelector('button');b.disabled=true;b.textContent='Comprobando con Instagram…';">
<textarea name="cookies" rows="4" required placeholder="Pega aquí las cookies: sessionid, csrftoken y ds_user_id (vale JSON, «sessionid=…; csrftoken=…» o una por línea)" style="width:100%;box-sizing:border-box;font-family:monospace;font-size:12px" autocomplete="off" spellcheck="false"></textarea>
<button class="mini" style="padding:7px 12px;margin-top:6px">Guardar sesión</button></form>
{% if ig_own %}<form method="post" action="{{ url_for('ig_session_clear') }}" style="margin-top:6px"><button class="mini">Borrar sesión</button></form>{% endif %}
<details style="margin-top:8px"><summary>¿De dónde saco las cookies?</summary>
<p>Entra en <b>instagram.com</b> con la cuenta nueva en el PC → F12 → pestaña <b>Aplicación</b> (Chrome) o <b>Almacenamiento</b> (Firefox) → Cookies → instagram.com. Copia el valor de <code>sessionid</code>, <code>csrftoken</code> y <code>ds_user_id</code> y pégalos aquí. Se comprueban contra Instagram antes de guardarlos. No cierres la sesión en el navegador, o la cookie dejará de valer.</p></details>
</section>{% endif %}
</body></html>"""


def _ago(ts, tz):
    if not ts:
        return "—"
    d = dt.datetime.fromtimestamp(ts, ZoneInfo(tz))
    now = dt.datetime.now(ZoneInfo(tz))
    diff = now - d
    if diff.days >= 1:
        return d.strftime("%d/%m")
    h = diff.seconds // 3600
    return f"hace {h} h" if h else f"hace {max(1, diff.seconds // 60)} min"


def create_app(db, cfg, sources, run_now_cb, hooks=None):
    app = Flask(__name__)
    tz = cfg.get("timezone", "Europe/Madrid")
    ig_src = next((s for s in sources if s.platform == "instagram"), None)
    sections = [{"key": str(x["key"]), "label": x.get("label") or str(x["key"])} for x in (cfg.get("sections") or [])]
    # grupos de categorías por sección: {key: [{"title": "Marcas", "items": [{"label":..., "slugs":[...]}]}]}
    sec_groups = {}
    for x in (cfg.get("sections") or []):
        gs = []
        for g in (x.get("groups") or []):
            its = [{"label": str(lbl), "slugs": [str(v) for v in (v if isinstance(v, list) else [v])]}
                   for lbl, v in (g.get("items") or {}).items()]
            if its:
                gs.append({"title": g.get("title", "Categorías"), "items": its})
        if gs:
            sec_groups[str(x["key"])] = gs
    import inspect
    try:
        _accepts_slow = "include_slow" in inspect.signature(run_now_cb).parameters
    except (TypeError, ValueError):
        _accepts_slow = False
    media_root = os.path.join(os.path.dirname(os.path.abspath(cfg.get("db_path", "data/radar.db"))), "media")

    @app.get("/")
    def home():
        # la primera pestaña (la de más a la izquierda) es la de inicio
        if sections:
            return redirect(url_for("section_tab", key=sections[0]["key"]))
        if ig_src:
            return redirect(url_for("instagram_tab"))
        return redirect(url_for("index"))

    @app.get("/tiendas")
    def index():
        return render("radar")

    @app.get("/s/<key>")
    def section_tab(key):
        if key not in {x["key"] for x in sections}:
            return redirect(url_for("index"))
        return render("sec:" + key)

    @app.get("/instagram")
    def instagram_tab():
        if not ig_src:
            return redirect(url_for("index"))
        return render("ig")

    @app.post("/ig/run")
    def ig_run():
        run_now_cb(include_slow=True) if _accepts_slow else run_now_cb()
        return redirect(url_for("instagram_tab"))

    def render(tab):
        brand = request.args.get("brand") or None
        status = request.args.get("status") or None
        q = request.args.get("q") or None
        source = request.args.get("source") if tab != "ig" else None
        sec_key = tab[4:] if tab.startswith("sec:") else None
        sec_names = [x.name for x in sources if x.section == sec_key] if sec_key else []
        hidden = [x.name for x in sources if x.section or x.platform == "instagram"]
        src = None
        cat = request.args.get("cat") or None
        groups = sec_groups.get(sec_key, []) if sec_key else []
        cat_slugs = None
        for g in groups:
            for c in g["items"]:
                if c["label"] == cat:
                    cat_slugs = c["slugs"]
        if cat and not cat_slugs:
            cat = None
        if tab == "ig":
            rows = db.list_items(brand=brand, status=status, q=q, limit=300, source=ig_src.name)
        elif sec_key:
            rows = db.list_items(brand=brand, status=status, q=q, limit=300, source=source or None,
                                 sources_in=sec_names, cats_any=cat_slugs)
        elif source:
            rows = db.list_items(brand=brand, status=status, q=q, limit=300, source=source)
        else:
            rows = db.list_items(brand=brand, status=status, q=q, limit=300, exclude_source=hidden)
        for r in rows:
            r["price_txt"] = fmt_price(r["price"], r["currency"])
            r["seen"] = _ago(r["first_seen"], tz)
        st = db.sources()
        src_rows = []
        for s in sources:
            if sec_key and s.section != sec_key:
                continue
            info = st.get(s.name, {})
            src_rows.append({"name": s.name, "count": info.get("last_count") or 0,
                             "error": info.get("last_error"), "when": _ago(info.get("last_ok"), tz),
                             "custom": bool(s.options.get("_custom")), "enabled": s.enabled})
        counts = db.count_by_source()
        web_chips = [{"name": s.name, "count": counts.get(s.name, 0)} for s in sources
                     if s.platform != "instagram" and (s.enabled or counts.get(s.name))
                     and ((s.section == sec_key) if sec_key else not s.section)]

        cat_rows = []
        for g in groups:
            its = []
            for c in g["items"]:
                n = db.count_cats(sec_names, c["slugs"])
                if n:
                    its.append({"label": c["label"], "count": n})
            if its:
                cat_rows.append({"title": g["title"], "chips": its})

        def link(**kw):
            args = {"brand": brand, "status": status, "q": q, "source": source, "cat": cat}
            args.update(kw)
            ep = "instagram_tab" if tab == "ig" else ("section_tab" if sec_key else "index")
            extra = {"key": sec_key} if sec_key else {}
            return url_for(ep, **extra, **{k: v for k, v in args.items() if v})

        ig = ig_context()
        return render_template_string(PAGE, items=rows, brands=BRANDS, order=ORDER, brand=brand,
                                      status=status, q=q, src=src, status_label=STATUS_LABEL, sel_web=source, sections=sections,
                                      web_chips=web_chips, cat=cat, cat_rows=cat_rows, src_msg=request.args.get("smsg"),
                                      sources=src_rows, link=link, tab=tab, **ig)

    # ---------------- Instagram
    def ig_context():
        if not ig_src:
            return {"ig_on": False}
        from .sources import instagram
        from . import ocr
        st = instagram.state(ig_src).get("accounts", {})
        accs = []
        for a in instagram.accounts(ig_src):
            s = st.get(a["user"], {})
            accs.append({**a, "missing": s.get("missing"), "error": s.get("error"),
                         "when": _ago(s.get("last_ok"), tz) if s.get("last_ok") else None})
        err = db.sources().get(ig_src.name, {}).get("last_error")
        sess = instagram.session_info(ig_src)
        fa = instagram.following_at(ig_src)
        return {"ig_on": True, "ig_accounts": accs, "ig_own": bool(sess),
                "ig_session": (sess or {}).get("user") or ("" if sess is None and not ig_src.options.get("account") else ig_src.options.get("account")),
                "ig_session_when": _ago(sess["saved"], tz) if sess and sess.get("saved") else None,
                "ig_mode": instagram.mode(ig_src), "ig_following_when": _ago(fa, tz) if fa else None,
                "ig_msg": request.args.get("msg"),
                "ig_err": err, "ig_every": ig_src.every_minutes, "ig_ocr": ocr.available()}

    def _ig_edit(fn):
        from .sources import instagram
        accs = instagram.accounts(ig_src)
        accs = fn(accs, instagram)
        instagram.save_accounts(ig_src, accs)
        return redirect(url_for("instagram_tab"))

    @app.post("/ig/add")
    def ig_add():
        if not ig_src:
            abort(404)
        def add(accs, instagram):
            new = instagram._norm_account({"user": request.form.get("user", ""),
                                           "brand": request.form.get("brand") or None,
                                           "kind": request.form.get("kind") or "news"})
            if new["user"] and all(a["user"] != new["user"] for a in accs):
                accs.append(new)
            # si estaba marcada como inexistente, que se vuelva a probar
            stp = instagram._paths(ig_src)["state"]
            stt = instagram.state(ig_src)
            if new["user"] in stt.get("accounts", {}):
                stt["accounts"][new["user"]].pop("missing", None)
                instagram._save(stp, stt)
            return accs
        return _ig_edit(add)

    @app.post("/ig/remove")
    def ig_remove():
        if not ig_src:
            abort(404)
        user = request.form.get("user")
        return _ig_edit(lambda accs, _: [a for a in accs if a["user"] != user])

    @app.post("/ig/toggle")
    def ig_toggle():
        if not ig_src:
            abort(404)
        user = request.form.get("user")
        def toggle(accs, _):
            for a in accs:
                if a["user"] == user:
                    a["enabled"] = not a.get("enabled", True)
            return accs
        return _ig_edit(toggle)

    # ---------------- webs añadidas desde el panel
    def _custom_path():
        from . import custom
        return custom.path_for(cfg), custom

    def _back(msg):
        return redirect(url_for("index", smsg=msg))

    @app.post("/src/add")
    def src_add():
        if not hooks:
            abort(404)
        path, custom = _custom_path()
        try:
            d = custom.from_url(request.form.get("url"), request.form.get("name"),
                                request.form.get("brand") or None, request.form.get("currency") or "EUR",
                                bool(request.form.get("only_preorder")))
        except ValueError as e:
            return _back("⚠ " + str(e))
        if any(s.name.lower() == d["name"].lower() for s in sources):
            return _back(f"⚠ Ya existe una fuente llamada «{d['name']}». Ponle otro nombre.")
        src = Source.from_dict(d)
        src.options.update(_custom=True, _base=os.path.dirname(os.path.abspath(path)), _data=os.path.dirname(path))
        try:
            platform, items = hooks["test"](src)
        except Exception as e:
            return _back(f"⚠ No he podido leer esa web: {str(e)[:160]}")
        if not items:
            return _back("⚠ La web responde pero no veo artículos. Prueba con el enlace de su sección de productos o preorders.")
        d["platform"] = platform
        src.platform = platform
        saved = custom.load(path)
        saved.append(d)
        custom.save(path, saved)
        hooks["add"](src)
        return _back(f"✔ Añadida «{d['name']}» ({platform}, {len(items)} artículos). Lo que ya tiene se guarda sin avisar; "
                     "solo te avisaré de lo nuevo.")

    @app.post("/src/remove")
    def src_remove():
        if not hooks:
            abort(404)
        name = request.form.get("name", "")
        path, custom = _custom_path()
        custom.save(path, [d for d in custom.load(path) if d.get("name") != name])
        hooks["remove"](name)
        db.delete_source(name)
        return _back(f"Quitada «{name}».")

    @app.post("/src/toggle")
    def src_toggle():
        if not hooks:
            abort(404)
        name = request.form.get("name", "")
        path, custom = _custom_path()
        saved = custom.load(path)
        for d in saved:
            if d.get("name") == name:
                d["enabled"] = not d.get("enabled", True)
                for s in sources:
                    if s.name == name:
                        s.enabled = d["enabled"]
        custom.save(path, saved)
        return _back("")

    @app.post("/ig/session")
    def ig_session():
        if not ig_src:
            abort(404)
        from .sources import instagram
        try:
            user = instagram.session_save(ig_src, request.form.get("cookies", ""))
        except ValueError as e:
            return redirect(url_for("instagram_tab", msg="⚠ " + str(e)) + "#sesion")
        except Exception as e:
            return redirect(url_for("instagram_tab", msg="⚠ No se pudo comprobar: " + str(e)[:200]) + "#sesion")
        if instagram.mode(ig_src) == "following":
            _bg_sync()
        return redirect(url_for("instagram_tab", msg=f"✔ Sesión de @{user} guardada. Sincronizando a quién sigues…") + "#sesion")

    @app.post("/ig/session/clear")
    def ig_session_clear():
        if not ig_src:
            abort(404)
        from .sources import instagram
        instagram.session_clear(ig_src)
        return redirect(url_for("instagram_tab", msg="Sesión borrada.") + "#sesion")

    @app.post("/ig/mode")
    def ig_mode():
        if not ig_src:
            abort(404)
        from .sources import instagram
        m = "manual" if request.form.get("mode") == "manual" else "following"
        instagram.save_accounts(ig_src, instagram.accounts(ig_src), mode=m)
        if m == "following":
            _bg_sync()
        return redirect(url_for("instagram_tab"))

    @app.post("/ig/sync")
    def ig_sync():
        if not ig_src:
            abort(404)
        _bg_sync()
        return redirect(url_for("instagram_tab", msg="Sincronizando a quién sigues… recarga en unos segundos."))

    def _bg_sync():
        import threading
        from .sources import instagram

        def work():
            try:
                bot, ig = instagram.client(ig_src, fresh=True)
                instagram.sync_following(ig_src, ig)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning("[Instagram] sincronizar seguidos: %s", e)
        threading.Thread(target=work, daemon=True).start()

    @app.get("/media/<path:rel>")
    def media(rel):
        return send_from_directory(media_root, rel, max_age=86400)

    @app.post("/run")
    def run_now():
        run_now_cb()
        return redirect(request.referrer or url_for("index"))

    @app.get("/api/items")
    def api_items():
        return jsonify(db.list_items(brand=request.args.get("brand"), status=request.args.get("status"),
                                     source=request.args.get("source"), q=request.args.get("q"),
                                     limit=int(request.args.get("limit", 200))))

    @app.get("/api/events")
    def api_events():
        """Long-poll para la APK.
        ?after=<id>  devuelve eventos posteriores; espera hasta ?wait= segundos si no hay.
        Sin 'after' (primera conexión) solo devuelve el último id, para no soltar el histórico.
        En horas de silencio retiene los avisos (llegan cuando acaban)."""
        after = request.args.get("after", type=int)
        last = db.max_event_id()
        if after is None or after < 0:
            return jsonify({"last_id": last, "events": [], "quiet": False})
        if after > last:          # la BD se reinició: reengancha
            return jsonify({"last_id": last, "events": [], "quiet": False})
        wait = max(0, min(request.args.get("wait", default=50, type=int), 55))
        deadline = time.time() + wait
        quiet_spec = (cfg.get("notify") or {}).get("quiet_hours", "")
        while True:
            quiet = in_quiet_hours(quiet_spec, tz)
            evs = [] if quiet else db.events_after(after)
            if evs or time.time() >= deadline:
                break
            time.sleep(2)
        for e in evs:
            e["brand_label"] = brand_label(e["brand"])
            e["kind_label"] = KIND_LABEL.get(e["kind"], e["kind"])
            e["status_label"] = STATUS_LABEL.get(e["status"], e["status"])
            e["price_txt"] = fmt_price(e["price"], e["currency"])
        new_last = evs[-1]["event_id"] if evs else after
        return jsonify({"last_id": new_last, "events": evs, "quiet": quiet,
                        "panel_url": (cfg.get("notify") or {}).get("panel_url", "")})

    @app.post("/api/test-event")
    def api_test_event():
        """Crea un aviso de prueba con el último artículo guardado (botón 'Probar' de la APK)."""
        rows = db.list_items(limit=1)
        if not rows:
            return jsonify({"ok": False, "error": "Aún no hay artículos guardados"}), 404
        db.add_event(rows[0]["uid"], "test")
        return jsonify({"ok": True})

    @app.get("/api/sources")
    def api_sources():
        return jsonify(db.sources())

    @app.get("/health")
    def health():
        return {"ok": True}

    return app
