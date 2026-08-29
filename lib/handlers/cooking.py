"""Cooking history and cross-device cooking state handlers, scoped per user."""
from ..db import get_db, slim_row, find_recipe
from ..sanitize import clamp_int, sanitize_str


def _history_list(self, params=None):
    db = get_db()
    uid = self.user_id
    rows = db.execute("""
        SELECT r.*, h.cooked_at FROM vault.cooking_history h
        JOIN visible_recipes r ON r.id=h.recipe_id
        WHERE h.user_id=? AND (r.owner='' OR r.owner=?)
        ORDER BY h.cooked_at DESC LIMIT 50
    """, [uid, uid]).fetchall()
    # Batch note lookup
    ids = [r["id"] for r in rows]
    noted = set()
    if ids:
        placeholders = ",".join("?" * len(ids))
        noted = set(r[0] for r in db.execute(
            f"SELECT recipe_id FROM vault.recipe_notes WHERE user_id=? AND recipe_id IN ({placeholders})",
            [uid] + ids).fetchall())
    self._json({"history": [{"recipe": slim_row(r, noted), "cooked_at": r["cooked_at"]} for r in rows]})

def _mark_cooked(self, rid):
    db = get_db()
    # Don't record history for a recipe this vault cannot see.
    if not find_recipe(db, rid, self.user_id):
        return self._json({"error": "not found"}, 404)
    db.execute("INSERT INTO vault.cooking_history(user_id,recipe_id) VALUES(?,?)", [self.user_id, rid])
    db.commit()
    self._json({"ok": True})

def _cooking_state_get(self, params):
    db = get_db()
    row = db.execute("SELECT recipe_id, step FROM vault.cooking_state WHERE user_id=?", [self.user_id]).fetchone()
    if row and row["recipe_id"]:
        self._json({"recipe_id": row["recipe_id"], "step": row["step"]})
    else:
        self._json({"recipe_id": None})

def _cooking_state_save(self, req):
    db = get_db()
    rid = sanitize_str(req.get("recipe_id"), 64)
    step = clamp_int(req.get("step"), 0, 0, 500)
    if rid:
        db.execute("INSERT OR REPLACE INTO vault.cooking_state(user_id,recipe_id,step,updated_at)"
                   " VALUES(?,?,?,datetime('now'))", [self.user_id, rid, step])
    else:
        db.execute("DELETE FROM vault.cooking_state WHERE user_id=?", [self.user_id])
    db.commit()
    self._json({"ok": True})
