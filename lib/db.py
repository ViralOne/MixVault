"""Database access, FTS helpers, and row formatters."""
import json, re, sqlite3, threading
from .config import DB_PATH

local = threading.local()

def get_db():
    if not hasattr(local, "db"):
        local.db = sqlite3.connect(DB_PATH)
        local.db.row_factory = sqlite3.Row
        local.db.execute("PRAGMA journal_mode=WAL")
        # Ensure extra tables exist
        local.db.executescript("""
            CREATE TABLE IF NOT EXISTS favorites (
                recipe_id TEXT PRIMARY KEY,
                added_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS recent (
                recipe_id TEXT PRIMARY KEY,
                viewed_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS shopping_list (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item TEXT NOT NULL,
                recipe_id TEXT,
                recipe_name TEXT DEFAULT '',
                checked INTEGER DEFAULT 0,
                added_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS cooking_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recipe_id TEXT NOT NULL,
                cooked_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (recipe_id) REFERENCES recipes(id)
            );
            CREATE TABLE IF NOT EXISTS recipe_notes (
                recipe_id TEXT PRIMARY KEY,
                note TEXT NOT NULL,
                updated_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (recipe_id) REFERENCES recipes(id)
            );
            CREATE TABLE IF NOT EXISTS cooking_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                recipe_id TEXT,
                step INTEGER DEFAULT 0,
                updated_at TEXT DEFAULT (datetime('now'))
            );
        """)
        # Migration: add recipe_name column if missing
        try:
            local.db.execute("SELECT recipe_name FROM shopping_list LIMIT 0")
        except Exception:
            local.db.execute("ALTER TABLE shopping_list ADD COLUMN recipe_name TEXT DEFAULT ''")
            local.db.commit()
    return local.db


def _fts_escape(q):
    """Escape FTS5 special chars and build prefix query."""
    words = []
    for w in q.split():
        w = w.strip()
        if not w:
            continue
        # Remove FTS5 special chars
        clean = ''.join(c for c in w if c.isalnum() or c in '-_')
        if clean:
            words.append('"' + clean + '"*')
    return ' '.join(words) if words else None

def slim_row(row, noted_ids=None):
    return {
        "id":row["id"],"name":row["name"],"country":row["country"],
        "lang":row["lang"],"collection":row["collection"],"image":row["image"],
        "totalTime":row["total_time"],"yield":row["yield"],
        "stepCount":len(json.loads(row["steps"])),
        "hasNote": row["id"] in noted_ids if noted_ids is not None else False,
    }

def slim_rows(rows):
    """Convert rows to slim dicts with batched hasNote lookup."""
    if not rows:
        return []
    db = get_db()
    ids = [r["id"] for r in rows]
    placeholders = ",".join("?" * len(ids))
    noted = set(r[0] for r in db.execute(
        f"SELECT recipe_id FROM recipe_notes WHERE recipe_id IN ({placeholders})", ids).fetchall())
    return [slim_row(r, noted) for r in rows]

_icon_cache = {}  # name -> icon_id

def _get_ingredient_icon(text):
    """Look up icon ID for an ingredient text. Uses fuzzy matching on last words."""
    if not _icon_cache:
        # Load cache on first call
        try:
            db = get_db()
            for r in db.execute("SELECT name, icon_id FROM ingredient_icons").fetchall():
                _icon_cache[r[0]] = r[1]
        except:
            pass
    if not _icon_cache:
        return None
    t = text.lower().strip()
    # Try exact match
    if t in _icon_cache:
        return _icon_cache[t]
    # Strip leading quantity (e.g. "200 g flour" -> "flour")
    stripped = re.sub(r'^[\d.,/½¼¾⅓⅔]+\s*(g|kg|ml|l|dl|cl|oz|lb|tsp|tbsp|cup|cups|piece|pieces|pcs|stk|stück|ks|buc|unidades?)?\s*', '', t).strip()
    if stripped in _icon_cache:
        return _icon_cache[stripped]
    # Try last 1-3 words
    words = stripped.split()
    for n in range(1, min(4, len(words)+1)):
        key = ' '.join(words[-n:])
        if key in _icon_cache:
            return _icon_cache[key]
    return None

ICON_BASE = "https://assets.tmecosys.com/image/upload/t_web_ingredient_48x48/icons/ingredient_icons/"

def full_row(row):
    ingredients = json.loads(row["ingredients"])
    ing_icons = []
    for ing in ingredients:
        icon_id = _get_ingredient_icon(ing)
        ing_icons.append(f"{ICON_BASE}{icon_id}" if icon_id else None)
    return {
        "id":row["id"],"name":row["name"],"country":row["country"],
        "lang":row["lang"],"collection":row["collection"],"image":row["image"],
        "totalTime":row["total_time"],"yield":row["yield"],
        "categories":json.loads(row["categories"]),
        "ingredients":ingredients,
        "ingredient_icons":ing_icons,
        "steps":json.loads(row["steps"]),
        "nutrition":json.loads(row["nutrition"]),
        "keywords":row["keywords"],
    }
