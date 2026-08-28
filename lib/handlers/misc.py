"""Miscellaneous handlers: export, poll, health, share, notes."""
import html, time
from pathlib import Path
from ..config import DB_PATH, BACKUP_DIR, START_TIME
from ..db import get_db, full_row, find_recipe


def _export(self, params):
    """Export shopping list and notes as JSON."""
    db = get_db()
    uid = self.user_id
    shopping = [dict(r) for r in db.execute(
        "SELECT id, item, recipe_id, recipe_name, checked, added_at FROM vault.shopping_list"
        " WHERE user_id=? ORDER BY added_at DESC", [uid]).fetchall()]
    notes = [dict(r) for r in db.execute(
        "SELECT recipe_id, note, updated_at FROM vault.recipe_notes WHERE user_id=?", [uid]).fetchall()]
    favorites = [r[0] for r in db.execute(
        "SELECT recipe_id FROM vault.favorites WHERE user_id=?", [uid]).fetchall()]
    fmt = params.get("format", ["json"])[0]
    if fmt == "csv":
        import csv, io
        out = io.StringIO()
        w = csv.writer(out)
        w.writerow(["item", "recipe_name", "checked"])
        for s in shopping:
            w.writerow([s["item"], s.get("recipe_name",""), s["checked"]])
        body = out.getvalue().encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/csv")
        self.send_header("Content-Disposition", "attachment; filename=shopping_list.csv")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)
    else:
        self._json({"shopping": shopping, "notes": notes, "favorites": favorites})

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
    backups = sorted(BACKUP_DIR.glob("recipes_*.db"))
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
    note = req.get("note", "").strip()
    if note:
        db.execute("INSERT OR REPLACE INTO vault.recipe_notes(user_id,recipe_id,note,updated_at)"
                   " VALUES(?,?,?,datetime('now'))", [self.user_id, rid, note])
    else:
        db.execute("DELETE FROM vault.recipe_notes WHERE user_id=? AND recipe_id=?", [self.user_id, rid])
    db.commit()
    self._json({"ok": True})

def _restore(self, req):
    """Restore favorites, notes, shopping list from backup JSON."""
    db = get_db()
    uid = self.user_id
    if req.get("favorites"):
        for rid in req["favorites"]:
            db.execute("INSERT OR IGNORE INTO vault.favorites(user_id,recipe_id) VALUES(?,?)", [uid, str(rid)])
    if req.get("notes"):
        for n in req["notes"]:
            if n.get("recipe_id") and n.get("note"):
                db.execute("INSERT OR REPLACE INTO vault.recipe_notes(user_id,recipe_id,note,updated_at)"
                           " VALUES(?,?,?,datetime('now'))", [uid, n["recipe_id"], n["note"]])
    if req.get("shopping"):
        for s in req["shopping"]:
            if s.get("item"):
                db.execute("INSERT INTO vault.shopping_list(user_id,item,recipe_id,recipe_name,checked) VALUES(?,?,?,?,?)",
                           [uid, s["item"], s.get("recipe_id",""), s.get("recipe_name",""), s.get("checked",0)])
    db.commit()
    self._json({"ok": True})

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
    tags = req.get("tags", [])
    db.execute("DELETE FROM vault.recipe_tags WHERE user_id=? AND recipe_id=?", [self.user_id, rid])
    for t in tags:
        t = str(t).strip()
        if t:
            db.execute("INSERT OR IGNORE INTO vault.recipe_tags(user_id,recipe_id,tag) VALUES(?,?,?)",
                       [self.user_id, rid, t])
    db.commit()
    self._json({"ok": True})
