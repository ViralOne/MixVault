"""Shopping list handlers."""
from ..db import get_db


def _shopping_list(self, params=None):
    db = get_db()
    rows = db.execute("SELECT * FROM shopping_list ORDER BY added_at DESC").fetchall()
    self._json({"items": [dict(r) for r in rows]})

def _shopping_add(self, req):
    db = get_db()
    items = req.get("items", [])
    rid = str(req.get("recipe_id", ""))
    rname = str(req.get("recipe_name", ""))
    for item in items:
        if isinstance(item, str) and item.strip():
            db.execute("INSERT INTO shopping_list(item,recipe_id,recipe_name) VALUES(?,?,?)", [item.strip(), rid, rname])
    db.commit()
    _shopping_list(self)

def _shopping_toggle(self, req):
    db = get_db()
    sid = req.get("id")
    if sid:
        db.execute("UPDATE shopping_list SET checked=NOT checked WHERE id=?", [sid])
        db.commit()
    _shopping_list(self)

def _shopping_clear(self, req):
    db = get_db()
    mode = req.get("mode", "checked")
    # Fetch items before deleting (for undo support)
    if mode == "all":
        deleted = db.execute("SELECT * FROM shopping_list").fetchall()
        db.execute("DELETE FROM shopping_list")
    else:
        deleted = db.execute("SELECT * FROM shopping_list WHERE checked=1").fetchall()
        db.execute("DELETE FROM shopping_list WHERE checked=1")
    db.commit()
    rows = db.execute("SELECT * FROM shopping_list ORDER BY added_at DESC").fetchall()
    self._json({"items": [dict(r) for r in rows], "deleted": [dict(r) for r in deleted]})

def _shopping_restore(self, req):
    """Restore previously deleted shopping items (undo)."""
    db = get_db()
    items = req.get("items", [])
    for item in items:
        if isinstance(item, dict) and item.get("item"):
            db.execute("INSERT INTO shopping_list(item,recipe_id,recipe_name,checked) VALUES(?,?,?,?)",
                       [item["item"], item.get("recipe_id",""), item.get("recipe_name",""), item.get("checked",0)])
    db.commit()
    _shopping_list(self)

def _shopping_delete(self, req):
    db = get_db()
    sid = req.get("id")
    if sid:
        db.execute("DELETE FROM shopping_list WHERE id=?", [sid])
        db.commit()
    _shopping_list(self)
