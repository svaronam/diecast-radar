"""SQLite: artículos vistos, eventos (avisos pendientes) y estado de cada fuente."""
import os
import sqlite3
import threading
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    uid TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    key TEXT NOT NULL,
    brand TEXT,
    title TEXT NOT NULL,
    url TEXT,
    image TEXT,
    price REAL,
    currency TEXT,
    sku TEXT,
    status TEXT,
    first_seen INTEGER,
    last_seen INTEGER,
    status_changed INTEGER
);
CREATE INDEX IF NOT EXISTS idx_items_source ON items(source);
CREATE INDEX IF NOT EXISTS idx_items_first ON items(first_seen DESC);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid TEXT NOT NULL,
    kind TEXT NOT NULL,          -- new | preorder_open | restock
    created INTEGER NOT NULL,
    sent INTEGER NOT NULL DEFAULT 0   -- 0 pendiente, 1 enviado, 2 en resumen
);
CREATE INDEX IF NOT EXISTS idx_events_sent ON events(sent);

CREATE TABLE IF NOT EXISTS sources (
    name TEXT PRIMARY KEY,
    last_run INTEGER,
    last_ok INTEGER,
    last_error TEXT,
    last_count INTEGER,
    platform TEXT
);
"""


def _cat_cond(c):
    # "~texto" = el título contiene ese texto; lo demás = categoría/marca guardada
    return "title LIKE ?" if c.startswith("~") else "cats LIKE ?"


def _cat_args(c):
    return [f"%{c[1:]}%"] if c.startswith("~") else [f"%|{c}|%"]


class DB:
    def __init__(self, path: str):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        with self.lock:
            self.conn.executescript(SCHEMA)
            self.conn.execute("PRAGMA journal_mode=WAL")
            try:
                self.conn.execute("ALTER TABLE items ADD COLUMN cats TEXT")
            except sqlite3.OperationalError:
                pass  # ya existe
            self._migrate()
            self.conn.commit()

    def _migrate(self):
        """v1: las primeras pasadas se guardaron con segundos distintos y quedaban al revés.
        Se unifica la hora de cada lote inicial (lo que cae a menos de 3 min del primer artículo de su fuente)."""
        if self.conn.execute("PRAGMA user_version").fetchone()[0] >= 1:
            return
        self.conn.execute("""UPDATE items SET first_seen = (SELECT MIN(i2.first_seen) FROM items i2 WHERE i2.source = items.source)
                             WHERE source NOT LIKE 'Instagram%'
                               AND first_seen - (SELECT MIN(i2.first_seen) FROM items i2 WHERE i2.source = items.source) < 180""")
        self.conn.execute("PRAGMA user_version = 1")

    # ---------- items ----------
    def count_source(self, source: str) -> int:
        with self.lock:
            return self.conn.execute("SELECT COUNT(*) FROM items WHERE source=?", (source,)).fetchone()[0]

    def get(self, uid: str):
        with self.lock:
            return self.conn.execute("SELECT * FROM items WHERE uid=?", (uid,)).fetchone()

    def insert(self, it, now=None):
        now = now or int(time.time())
        with self.lock:
            self.conn.execute(
                """INSERT INTO items (uid, source, key, brand, title, url, image, price, currency, sku,
                                      status, first_seen, last_seen, status_changed, cats)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (it.uid, it.source, it.key, it.brand, it.title, it.url, it.image, it.price,
                 it.currency, it.sku, it.status, now, now, now, it.categories or None))
            self.conn.commit()

    def update(self, it, status_changed: bool, now=None):
        now = now or int(time.time())
        with self.lock:
            self.conn.execute(
                """UPDATE items SET title=?, url=?, image=COALESCE(?, image), price=?, sku=COALESCE(?, sku),
                                    status=?, brand=COALESCE(?, brand), last_seen=?,
                                    status_changed=CASE WHEN ? THEN ? ELSE status_changed END,
                                    cats=COALESCE(?, cats)
                   WHERE uid=?""",
                (it.title, it.url, it.image, it.price, it.sku, it.status, it.brand, now,
                 1 if status_changed else 0, now, it.categories or None, it.uid))
            self.conn.commit()

    def url_seen_elsewhere(self, url: str, source: str) -> bool:
        """Mismo producto ya visto en otra sección de la misma tienda (evita avisos dobles)."""
        with self.lock:
            return self.conn.execute("SELECT 1 FROM items WHERE url=? AND source<>? LIMIT 1",
                                     (url, source)).fetchone() is not None

    def list_items(self, brand=None, status=None, source=None, q=None, limit=200, exclude_source=None,
                   sources_in=None, cats_any=None):
        sql, args = "SELECT * FROM items WHERE 1=1", []
        if exclude_source:
            ex = [exclude_source] if isinstance(exclude_source, str) else list(exclude_source)
            if ex:
                sql += " AND source NOT IN (%s)" % ",".join("?" * len(ex)); args += ex
        if sources_in is not None:
            if not sources_in:
                return []
            sql += " AND source IN (%s)" % ",".join("?" * len(sources_in)); args += list(sources_in)
        if cats_any:
            sql += " AND (" + " OR ".join(_cat_cond(c) for c in cats_any) + ")"
            args += [a for c in cats_any for a in _cat_args(c)]
        if brand:
            sql += " AND brand=?"; args.append(brand)
        if status:
            sql += " AND status=?"; args.append(status)
        if source:
            sql += " AND source=?"; args.append(source)
        if q:
            sql += " AND (title LIKE ? OR sku LIKE ?)"; args += [f"%{q}%", f"%{q}%"]
        sql += " ORDER BY first_seen DESC, CAST(key AS INTEGER) DESC, rowid ASC LIMIT ?"
        args.append(limit)
        with self.lock:
            return [dict(r) for r in self.conn.execute(sql, args).fetchall()]

    def count_cats(self, sources_in, cats):
        """Cuántos artículos de esas fuentes llevan alguna de esas categorías."""
        if not sources_in or not cats:
            return 0
        sql = ("SELECT COUNT(*) FROM items WHERE source IN (%s) AND (%s)" %
               (",".join("?" * len(sources_in)), " OR ".join(_cat_cond(c) for c in cats)))
        with self.lock:
            return self.conn.execute(sql, list(sources_in) + [a for c in cats for a in _cat_args(c)]).fetchone()[0]

    def count_by_source(self):
        with self.lock:
            return {r[0]: r[1] for r in self.conn.execute("SELECT source, COUNT(*) FROM items GROUP BY source")}

    def delete_source(self, name):
        with self.lock:
            self.conn.execute("DELETE FROM events WHERE uid IN (SELECT uid FROM items WHERE source=?)", (name,))
            self.conn.execute("DELETE FROM items WHERE source=?", (name,))
            self.conn.execute("DELETE FROM sources WHERE name=?", (name,))
            self.conn.commit()

    # ---------- events ----------
    def add_event(self, uid: str, kind: str):
        with self.lock:
            self.conn.execute("INSERT INTO events (uid, kind, created) VALUES (?,?,?)",
                              (uid, kind, int(time.time())))
            self.conn.commit()

    def pending_events(self):
        with self.lock:
            return [dict(r) for r in self.conn.execute(
                """SELECT e.id AS event_id, e.kind, e.created, i.*
                   FROM events e JOIN items i ON i.uid = e.uid
                   WHERE e.sent = 0 ORDER BY e.id""").fetchall()]

    def max_event_id(self) -> int:
        with self.lock:
            return self.conn.execute("SELECT COALESCE(MAX(id), 0) FROM events").fetchone()[0]

    def events_after(self, after: int, limit: int = 50):
        """Para la APK: eventos con id > after (la app guarda su propio cursor)."""
        with self.lock:
            return [dict(r) for r in self.conn.execute(
                """SELECT e.id AS event_id, e.kind, e.created, i.uid, i.source, i.brand, i.title,
                          i.url, i.image, i.price, i.currency, i.sku, i.status
                   FROM events e JOIN items i ON i.uid = e.uid
                   WHERE e.id > ? ORDER BY e.id LIMIT ?""", (after, limit)).fetchall()]

    def mark_sent(self, event_ids, value=1):
        if not event_ids:
            return
        with self.lock:
            self.conn.executemany("UPDATE events SET sent=? WHERE id=?", [(value, i) for i in event_ids])
            self.conn.commit()

    # ---------- sources ----------
    def source_status(self, name, *, ok: bool, count=0, error=None, platform=None):
        now = int(time.time())
        with self.lock:
            self.conn.execute(
                """INSERT INTO sources (name, last_run, last_ok, last_error, last_count, platform)
                   VALUES (?,?,?,?,?,?)
                   ON CONFLICT(name) DO UPDATE SET
                     last_run=excluded.last_run,
                     last_ok=CASE WHEN ? THEN excluded.last_run ELSE sources.last_ok END,
                     last_error=excluded.last_error,
                     last_count=CASE WHEN ? THEN excluded.last_count ELSE sources.last_count END,
                     platform=COALESCE(excluded.platform, sources.platform)""",
                (name, now, now if ok else None, error, count, platform, ok, ok))
            self.conn.commit()

    def get_platform(self, name):
        with self.lock:
            r = self.conn.execute("SELECT platform FROM sources WHERE name=?", (name,)).fetchone()
            return r[0] if r else None

    def sources(self):
        with self.lock:
            return {r["name"]: dict(r) for r in self.conn.execute("SELECT * FROM sources").fetchall()}
