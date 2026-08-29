"""Shopping list handlers. Every row is scoped to the caller's user_id."""
from ..db import get_db
from ..sanitize import (MAX_SHOPPING_ITEM, MAX_SHOPPING_ITEMS_PER_CALL, clamp_int,
                        sanitize_list, sanitize_str)


def _rows(db, uid):
    return [dict(r) for r in db.execute(
        "SELECT id, item, recipe_id, recipe_name, checked, added_at FROM vault.shopping_list"
        " WHERE user_id=? ORDER BY added_at DESC", [uid]).fetchall()]


def _shopping_list(self, params=None):
    self._json({"items": _rows(get_db(), self.user_id)})

def _shopping_add(self, req):
    db = get_db()
    items = sanitize_list(req.get("items", []), MAX_SHOPPING_ITEMS_PER_CALL, MAX_SHOPPING_ITEM)
    rid = sanitize_str(req.get("recipe_id", ""), 64)
    rname = sanitize_str(req.get("recipe_name", ""), 200)
    for item in items:
        db.execute("INSERT INTO vault.shopping_list(user_id,item,recipe_id,recipe_name) VALUES(?,?,?,?)",
                   [self.user_id, item, rid, rname])
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
    if not isinstance(items, list):
        items = []
    for item in items[:MAX_SHOPPING_ITEMS_PER_CALL]:
        text = sanitize_str(item.get("item"), MAX_SHOPPING_ITEM) if isinstance(item, dict) else ""
        if text:
            db.execute("INSERT INTO vault.shopping_list(user_id,item,recipe_id,recipe_name,checked) VALUES(?,?,?,?,?)",
                       [self.user_id, text, sanitize_str(item.get("recipe_id"), 64),
                        sanitize_str(item.get("recipe_name"), 200),
                        clamp_int(item.get("checked"), 0, 0, 1)])
    db.commit()
    _shopping_list(self)

def _shopping_delete(self, req):
    db = get_db()
    sid = req.get("id")
    if sid:
        db.execute("DELETE FROM vault.shopping_list WHERE id=? AND user_id=?", [sid, self.user_id])
        db.commit()
    _shopping_list(self)
