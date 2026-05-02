"""Cooking history and cross-device cooking state handlers."""
from ..db import get_db, slim_row


def _history_list(self, params=None):
    db = get_db()
    rows = db.execute("""
        SELECT r.*, h.cooked_at FROM cooking_history h
        JOIN recipes r ON r.id=h.recipe_id
        ORDER BY h.cooked_at DESC LIMIT 50
    """).fetchall()
    # Batch note lookup
    ids = [r["id"] for r in rows]
    noted = set()
    if ids:
        placeholders = ",".join("?" * len(ids))
        noted = set(r[0] for r in db.execute(
            f"SELECT recipe_id FROM recipe_notes WHERE recipe_id IN ({placeholders})", ids).fetchall())
    self._json({"history": [{"recipe": slim_row(r, noted), "cooked_at": r["cooked_at"]} for r in rows]})

def _mark_cooked(self, rid):
    db = get_db()
    db.execute("INSERT INTO cooking_history(recipe_id) VALUES(?)", [rid])
    db.commit()
    self._json({"ok": True})

def _cooking_state_get(self, params):
    db = get_db()
    row = db.execute("SELECT recipe_id, step FROM cooking_state WHERE id=1").fetchone()
    if row and row["recipe_id"]:
        self._json({"recipe_id": row["recipe_id"], "step": row["step"]})
    else:
        self._json({"recipe_id": None})

def _cooking_state_save(self, req):
    db = get_db()
    rid = req.get("recipe_id")
    step = req.get("step", 0)
    if rid:
        db.execute("INSERT OR REPLACE INTO cooking_state(id,recipe_id,step,updated_at) VALUES(1,?,?,datetime('now'))", [rid, step])
    else:
        db.execute("DELETE FROM cooking_state WHERE id=1")
    db.commit()
    self._json({"ok": True})
