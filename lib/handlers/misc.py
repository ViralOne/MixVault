"""Miscellaneous handlers: export, poll, health, share, notes."""
import json, time
from pathlib import Path
from ..config import log, DB_PATH, BACKUP_DIR, START_TIME
from ..db import get_db, full_row


def _export(self, params):
    """Export shopping list and notes as JSON."""
    db = get_db()
    shopping = [dict(r) for r in db.execute("SELECT * FROM shopping_list ORDER BY added_at DESC").fetchall()]
    notes = [dict(r) for r in db.execute("SELECT * FROM recipe_notes").fetchall()]
    favorites = [r[0] for r in db.execute("SELECT recipe_id FROM favorites").fetchall()]
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
    shop_count = db.execute("SELECT count(*) FROM shopping_list").fetchone()[0]
    fav_count = db.execute("SELECT count(*) FROM favorites").fetchone()[0]
    self._json({"shopping_count": shop_count, "favorites_count": fav_count, "ts": int(time.time())})

def _health(self, params):
    """Health check with system details."""
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
    row = db.execute("SELECT * FROM recipes WHERE id=?", [rid]).fetchone()
    if not row:
        return self._json({"error": "not found"}, 404)
    r = full_row(row)
    ings_html = "".join(f"<li>{i}</li>" for i in r["ingredients"])
    steps_html = "".join(f"<li>{s}</li>" for i, s in enumerate(r["steps"]))
    nut_html = ""
    if r["nutrition"].get("calories"):
        nut_html = f'<p class="nut">{r["nutrition"]["calories"]} · {r["nutrition"].get("protein","")} protein · {r["nutrition"].get("carbs","")} carbs · {r["nutrition"].get("fat","")} fat</p>'
    html_page = f'''<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{r["name"]} - MixVault</title>
<style>*{{margin:0;padding:0;box-sizing:border-box}}body{{font-family:system-ui,sans-serif;max-width:640px;margin:0 auto;padding:20px;color:#1a1a1a}}
img{{width:100%;border-radius:12px;margin-bottom:16px}}h1{{font-size:24px;margin-bottom:8px}}
.meta{{color:#666;margin-bottom:16px;font-size:14px}}.nut{{background:#f1f8e9;padding:10px;border-radius:8px;font-size:13px;margin-bottom:16px}}
h2{{font-size:16px;color:#2e7d32;margin:20px 0 8px}}ul,ol{{padding-left:20px}}li{{margin-bottom:8px;line-height:1.5}}
.footer{{margin-top:32px;padding-top:16px;border-top:1px solid #e5e7eb;font-size:12px;color:#999;text-align:center}}</style></head>
<body>{"<img src='" + r["image"] + "'>" if r["image"] else ""}
<h1>{r["name"]}</h1><p class="meta">{r.get("yield","")} · {r["country"]}</p>{nut_html}
<h2>Ingredients</h2><ul>{ings_html}</ul>
<h2>Steps</h2><ol>{steps_html}</ol>
<div class="footer">Shared from MixVault</div></body></html>'''
    body = html_page.encode()
    self.send_response(200)
    self.send_header("Content-Type", "text/html")
    self.send_header("Content-Length", len(body))
    self.end_headers()
    self.wfile.write(body)

def _note_get(self, rid):
    db = get_db()
    row = db.execute("SELECT note FROM recipe_notes WHERE recipe_id=?", [rid]).fetchone()
    self._json({"note": row["note"] if row else ""})

def _note_save(self, rid, req):
    db = get_db()
    note = req.get("note", "").strip()
    if note:
        db.execute("INSERT OR REPLACE INTO recipe_notes(recipe_id,note,updated_at) VALUES(?,?,datetime('now'))", [rid, note])
    else:
        db.execute("DELETE FROM recipe_notes WHERE recipe_id=?", [rid])
    db.commit()
    self._json({"ok": True})
