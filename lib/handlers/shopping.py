"""Shopping list handlers. Every row is scoped to the caller's user_id."""
from ..db import get_db


def _rows(db, uid):
    return [dict(r) for r in db.execute(
        "SELECT id, item, recipe_id, recipe_name, checked, added_at FROM vault.shopping_list"
        " WHERE user_id=? ORDER BY added_at DESC", [uid]).fetchall()]


def _shopping_list(self, params=None):
    self._json({"items": _rows(get_db(), self.user_id)})

def _shopping_add(self, req):
    db = get_db()
    items = req.get("items", [])
    rid = str(req.get("recipe_id", ""))
    rname = str(req.get("recipe_name", ""))
    for item in items:
        if isinstance(item, str) and item.strip():
            db.execute("INSERT INTO vault.shopping_list(user_id,item,recipe_id,recipe_name) VALUES(?,?,?,?)",
                       [self.user_id, item.strip(), rid, rname])
    db.commit()
    _shopping_list(self)

def _shopping_toggle(self, req):
    db = get_db()
    sid = req.get("id")
    if sid:
        db.execute("UPDATE vault.shopping_list SET checked=NOT checked WHERE id=? AND user_id=?", [sid, self.user_id])
        db.commit()
    _shopping_list(self)

def _shopping_clear(self, req):
    db = get_db()
    mode = req.get("mode", "checked")
    # Fetch items before deleting (for undo support)
    if mode == "all":
        deleted = _rows(db, self.user_id)
        db.execute("DELETE FROM vault.shopping_list WHERE user_id=?", [self.user_id])
    else:
        deleted = [dict(r) for r in db.execute(
            "SELECT id, item, recipe_id, recipe_name, checked, added_at FROM vault.shopping_list"
            " WHERE user_id=? AND checked=1", [self.user_id]).fetchall()]
        db.execute("DELETE FROM vault.shopping_list WHERE user_id=? AND checked=1", [self.user_id])
    db.commit()
    self._json({"items": _rows(db, self.user_id), "deleted": deleted})

def _shopping_restore(self, req):
    """Restore previously deleted shopping items (undo)."""
    db = get_db()
    items = req.get("items", [])
    for item in items:
        if isinstance(item, dict) and item.get("item"):
            db.execute("INSERT INTO vault.shopping_list(user_id,item,recipe_id,recipe_name,checked) VALUES(?,?,?,?,?)",
                       [self.user_id, item["item"], item.get("recipe_id",""), item.get("recipe_name",""),
                        item.get("checked",0)])
    db.commit()
    _shopping_list(self)

def _shopping_delete(self, req):
    db = get_db()
    sid = req.get("id")
    if sid:
        db.execute("DELETE FROM vault.shopping_list WHERE id=? AND user_id=?", [sid, self.user_id])
        db.commit()
    _shopping_list(self)
