"""Miscellaneous handlers: export, poll, health, share, notes."""
import hashlib, html, time
from pathlib import Path
from ..config import DB_PATH, BACKUP_DIR, START_TIME
from ..db import get_db, full_row, find_recipe
from ..sanitize import (MAX_NOTE, MAX_TAG, MAX_TAGS_PER_RECIPE, json_text,
                        sanitize_list, sanitize_str)


def _csv_safe(value):
    """
    Neutralise spreadsheet formulas.

    A shopping item saved as `=HYPERLINK(...)` is inert in the app, but Excel and
    Sheets execute it on open. Prefixing an apostrophe keeps the text visible and
    the cell a string.
    """
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def _export(self, params):
    """
    Everything this vault owns, as JSON — or just the shopping list, as CSV.

    The recipe library is deliberately absent: it is shared, unchanged by you and
    already a single file you can copy (recipes.db). What cannot be reconstructed
    is what lives in the vault, so all of it goes here.
    """
    db = get_db()
    uid = self.user_id
    shopping = [dict(r) for r in db.execute(
        "SELECT id, item, recipe_id, recipe_name, checked, added_at FROM vault.shopping_list"
        " WHERE user_id=? ORDER BY added_at DESC", [uid]).fetchall()]

    fmt = params.get("format", ["json"])[0]
    if fmt == "csv":
        import csv, io
        out = io.StringIO()
        w = csv.writer(out)
        w.writerow(["item", "recipe_name", "checked"])
        for s in shopping:
            w.writerow([_csv_safe(s["item"]), _csv_safe(s.get("recipe_name", "")), s["checked"]])
        body = out.getvalue().encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/csv")
        self.send_header("Content-Disposition", "attachment; filename=shopping_list.csv")
        self.send_header("Content-Length", len(body))
        self.send_header("Cache-Control", "no-store, private")
        self.end_headers()
        self.wfile.write(body)
        return

    notes = [dict(r) for r in db.execute(
        "SELECT recipe_id, note, updated_at FROM vault.recipe_notes WHERE user_id=?", [uid]).fetchall()]
    favorites = [r[0] for r in db.execute(
        "SELECT recipe_id FROM vault.favorites WHERE user_id=?", [uid]).fetchall()]
    tags = [dict(r) for r in db.execute(
        "SELECT recipe_id, tag FROM vault.recipe_tags WHERE user_id=?", [uid]).fetchall()]
    history = [dict(r) for r in db.execute(
        "SELECT recipe_id, cooked_at FROM vault.cooking_history WHERE user_id=? ORDER BY cooked_at",
        [uid]).fetchall()]
    recipes = [dict(r) for r in db.execute(
        "SELECT id, name, country, lang, collection, image, total_time, yield, categories,"
        " ingredients, steps, nutrition, keywords, created_at FROM vault.user_recipes WHERE owner=?",
        [uid]).fetchall()]
    self._json({
        "version": 2,
        "exported_at": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
        "shopping": shopping, "notes": notes, "favorites": favorites,
        "tags": tags, "history": history, "recipes": recipes,
    })

def _poll(self, params):
    """Return last-modified timestamps for multi-device sync."""
    db = get_db()
    uid = self.user_id
    shop_count = db.execute("SELECT count(*) FROM vault.shopping_list WHERE user_id=?", [uid]).fetchone()[0]
    fav_count = db.execute("SELECT count(*) FROM vault.favorites WHERE user_id=?", [uid]).fetchone()[0]
    self._json({"shopping_count": shop_count, "favorites_count": fav_count, "ts": int(time.time())})

def _health(self, params):
    """
    Health check. Unauthenticated callers (container probes) only get liveness —
    sizes and backup counts are for signed-in operators.
    """
    if not getattr(self, "authed", False):
        return self._json({"status": "ok"})
    db_path = Path(DB_PATH)
    wal_path = Path(DB_PATH + "-wal")
    uptime_secs = int(time.time() - START_TIME)
    days, rem = divmod(uptime_secs, 86400)
    hours, rem = divmod(rem, 3600)
    mins, _ = divmod(rem, 60)
    # Latest backup age
    backups = sorted(BACKUP_DIR.glob("recipes_[0-9]*.db"))
    backup_age = None
    if backups:
        backup_age = int(time.time() - backups[-1].stat().st_mtime)
    self._json({
        "status": "ok",
        "uptime": f"{days}d {hours}h {mins}m",
        "uptime_seconds": uptime_secs,
        "db_size_mb": round(db_path.stat().st_size / 1048576, 1) if db_path.exists() else 0,
        "wal_size_mb": round(wal_path.stat().st_size / 1048576, 1) if wal_path.exists() else 0,
        "backup_count": len(backups),
        "last_backup_age_seconds": backup_age,
    })

def _share_recipe(self, rid):
    """Generate a standalone HTML page for sharing."""
    db = get_db()
    row = find_recipe(db, rid, self.user_id)
    if not row:
        return self._json({"error": "not found"}, 404)
    r = full_row(row)
    # Names, ingredients and steps are user-editable, so everything below is escaped.
    e = lambda v: html.escape(str(v or ""), quote=True)
    ings_html = "".join(f"<li>{e(i)}</li>" for i in r["ingredients"])
    steps_html = "".join(f"<li>{e(s)}</li>" for s in r["steps"])
    nut = r["nutrition"]
    nut_html = ""
    if nut.get("calories"):
        nut_html = (f'<p class="nut">{e(nut["calories"])} · {e(nut.get("protein"))} protein · '
                    f'{e(nut.get("carbs"))} carbs · {e(nut.get("fat"))} fat</p>')
    img_html = f'<img src="{e(r["image"])}" alt="">' if r["image"] else ""
    html_page = f'''<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(r["name"])} - MixVault</title>
<style>*{{margin:0;padding:0;box-sizing:border-box}}body{{font-family:system-ui,sans-serif;max-width:640px;margin:0 auto;padding:20px;color:#1a1a1a}}
img{{width:100%;border-radius:12px;margin-bottom:16px}}h1{{font-size:24px;margin-bottom:8px}}
.meta{{color:#666;margin-bottom:16px;font-size:14px}}.nut{{background:#f1f8e9;padding:10px;border-radius:8px;font-size:13px;margin-bottom:16px}}
h2{{font-size:16px;color:#2e7d32;margin:20px 0 8px}}ul,ol{{padding-left:20px}}li{{margin-bottom:8px;line-height:1.5}}
.footer{{margin-top:32px;padding-top:16px;border-top:1px solid #e5e7eb;font-size:12px;color:#999;text-align:center}}</style></head>
<body>{img_html}
<h1>{e(r["name"])}</h1><p class="meta">{e(r.get("yield",""))} · {e(r["country"])}</p>{nut_html}
<h2>Ingredients</h2><ul>{ings_html}</ul>
<h2>Steps</h2><ol>{steps_html}</ol>
<div class="footer">Shared from MixVault</div></body></html>'''
    body = html_page.encode()
    self.send_response(200)
    self.send_header("Content-Type", "text/html; charset=utf-8")
    self.send_header("Content-Length", len(body))
    # A recipe can be private to this vault; never let a shared cache keep it.
    self.send_header("Cache-Control", "no-store, private")
    self.send_header("Content-Security-Policy", "default-src 'none'; img-src https: data:; style-src 'unsafe-inline'")
    self.end_headers()
    self.wfile.write(body)

def _note_get(self, rid):
    db = get_db()
    row = db.execute("SELECT note FROM vault.recipe_notes WHERE user_id=? AND recipe_id=?",
                     [self.user_id, rid]).fetchone()
    self._json({"note": row["note"] if row else ""})

def _note_save(self, rid, req):
    db = get_db()
    note = sanitize_str(req.get("note", ""), MAX_NOTE)
    if note:
        db.execute("INSERT OR REPLACE INTO vault.recipe_notes(user_id,recipe_id,note,updated_at)"
                   " VALUES(?,?,?,datetime('now'))", [self.user_id, rid, note])
    else:
        db.execute("DELETE FROM vault.recipe_notes WHERE user_id=? AND recipe_id=?", [self.user_id, rid])
    db.commit()
    self._json({"ok": True})

_RESTORE_CAP = 5_000


def _rows_of(req, key, kind=dict):
    rows = req.get(key)
    if not isinstance(rows, list):
        return []
    return [r for r in rows[:_RESTORE_CAP] if isinstance(r, kind)]


def _restore(self, req):
    """
    Load a vault export back in. Everything lands in the *caller's* vault, so a
    backup can be restored into a fresh vault after a lost key. Repeated restores
    of the same file do not duplicate rows, except shopping items, which have no
    natural identity.

    Restored rows go through the same sanitising as a fresh import: a backup is a
    file the caller can edit, not a trusted channel into the database.
    """
    if not isinstance(req, dict):
        return self._json({"error": "that file is not a MixVault backup"}, 400)
    db = get_db()
    uid = self.user_id
    counts = dict.fromkeys(("favorites", "notes", "shopping", "tags", "history", "recipes"), 0)

    for rid in _rows_of(req, "favorites", str):
        rid = sanitize_str(rid, 64)
        if rid:
            db.execute("INSERT OR IGNORE INTO vault.favorites(user_id,recipe_id) VALUES(?,?)", [uid, rid])
            counts["favorites"] += 1

    for n in _rows_of(req, "notes"):
        rid, note = sanitize_str(n.get("recipe_id"), 64), sanitize_str(n.get("note"), MAX_NOTE)
        if rid and note:
            db.execute("INSERT OR REPLACE INTO vault.recipe_notes(user_id,recipe_id,note,updated_at)"
                       " VALUES(?,?,?,datetime('now'))", [uid, rid, note])
            counts["notes"] += 1

    for s in _rows_of(req, "shopping"):
        item = sanitize_str(s.get("item"), 200)
        if item:
            db.execute("INSERT INTO vault.shopping_list(user_id,item,recipe_id,recipe_name,checked)"
                       " VALUES(?,?,?,?,?)",
                       [uid, item, sanitize_str(s.get("recipe_id"), 64),
                        sanitize_str(s.get("recipe_name"), 200), 1 if s.get("checked") else 0])
            counts["shopping"] += 1

    for t in _rows_of(req, "tags"):
        rid, tag = sanitize_str(t.get("recipe_id"), 64), sanitize_str(t.get("tag"), MAX_TAG)
        if rid and tag:
            db.execute("INSERT OR IGNORE INTO vault.recipe_tags(user_id,recipe_id,tag) VALUES(?,?,?)",
                       [uid, rid, tag])
            counts["tags"] += 1

    for h in _rows_of(req, "history"):
        rid = sanitize_str(h.get("recipe_id"), 64)
        if not rid:
            continue
        cooked_at = sanitize_str(h.get("cooked_at"), 32) or None
        # Same recipe at the same instant is the same cook, however often you restore.
        dup = db.execute("SELECT 1 FROM vault.cooking_history WHERE user_id=? AND recipe_id=? AND cooked_at=?",
                         [uid, rid, cooked_at]).fetchone()
        if not dup:
            db.execute("INSERT INTO vault.cooking_history(user_id,recipe_id,cooked_at) VALUES(?,?,?)",
                       [uid, rid, cooked_at])
            counts["history"] += 1

    for r in _rows_of(req, "recipes"):
        rid, name = sanitize_str(r.get("id"), 64), sanitize_str(r.get("name"), 200)
        if not (rid and name):
            continue
        existing = db.execute("SELECT owner FROM vault.user_recipes WHERE id=?", [rid]).fetchone()
        if existing and existing["owner"] != uid:
            # The id is taken by another vault; give this copy its own.
            rid = hashlib.md5(f"{uid}:{name}:{r.get('created_at','')}".encode()).hexdigest()[:12]
        db.execute(
            "INSERT OR REPLACE INTO vault.user_recipes(id,owner,name,country,lang,collection,image,"
            "total_time,yield,categories,ingredients,steps,nutrition,keywords) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [rid, uid, name, sanitize_str(r.get("country", "Custom"), 50),
             sanitize_str(r.get("lang", "en"), 5), sanitize_str(r.get("collection", "My Recipes"), 100),
             sanitize_str(r.get("image", ""), 500), sanitize_str(r.get("total_time", ""), 20),
             sanitize_str(r.get("yield", ""), 50), json_text(r.get("categories"), "[]"),
             json_text(r.get("ingredients"), "[]"), json_text(r.get("steps"), "[]"),
             json_text(r.get("nutrition"), "{}"), sanitize_str(r.get("keywords", ""), 500)])
        counts["recipes"] += 1

    db.commit()
    self._json({"ok": True, "restored": counts})

def _tags_list(self, params=None):
    """All distinct tags with usage counts, for the browse filter."""
    db = get_db()
    rows = db.execute(
        "SELECT tag, count(*) AS n FROM vault.recipe_tags WHERE user_id=? GROUP BY tag ORDER BY n DESC, tag",
        [self.user_id]
    ).fetchall()
    self._json({"tags": [{"tag": r["tag"], "count": r["n"]} for r in rows]})

def _tags_get(self, rid):
    db = get_db()
    rows = db.execute("SELECT tag FROM vault.recipe_tags WHERE user_id=? AND recipe_id=?",
                      [self.user_id, rid]).fetchall()
    self._json({"tags": [r["tag"] for r in rows]})

def _tags_save(self, rid, req):
    db = get_db()
    tags = sanitize_list(req.get("tags", []), MAX_TAGS_PER_RECIPE, MAX_TAG)
    db.execute("DELETE FROM vault.recipe_tags WHERE user_id=? AND recipe_id=?", [self.user_id, rid])
    for t in tags:
        db.execute("INSERT OR IGNORE INTO vault.recipe_tags(user_id,recipe_id,tag) VALUES(?,?,?)",
                   [self.user_id, rid, t])
    db.commit()
    self._json({"ok": True, "tags": tags})
