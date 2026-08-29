"""
Database access, FTS helpers, and row formatters.

Two files, deliberately separated:

  recipes.db  — the shared recipe library and its FTS index. Holds nothing
                personal, so it can be copied or handed to someone else as-is.
                Written only when the library itself changes, plus once on
                startup if an older database still has personal tables to move.
  vault.db    — every trace of a person: access keys, favourites, cooking
                history, shopping list, notes, tags, resume state, and the
                recipes they imported or generated themselves.

Both are opened on one connection (`ATTACH`), so queries can still join across
them; vault tables are addressed as `vault.<table>`. A per-connection view,
`visible_recipes`, is the library plus every private recipe, tagged with an
`owner` column — callers filter it with `(owner='' OR owner=:me)`. Search takes a
different route: the library through FTS5, private recipes through
`search_user_recipes`, merged in `_search`.
"""
import json, os, re, sqlite3, threading
from .config import DB_PATH, VAULT_DB_PATH, log
from .sanitize import json_col

local = threading.local()
_migrated = threading.Event()
_migrate_lock = threading.Lock()

# Column order for the `visible_recipes` union: both halves must select the same
# columns in the same order.
RECIPE_COLUMNS = (
    'id', 'name', 'country', 'lang', 'collection', 'image', 'total_time',
    '"yield"', 'categories', 'ingredients', 'steps', 'nutrition', 'keywords',
)

_VAULT_SCHEMA = """
    CREATE TABLE IF NOT EXISTS vault.users (
        id TEXT PRIMARY KEY,
        key_hash TEXT NOT NULL UNIQUE,
        label TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS vault.favorites (
        user_id TEXT NOT NULL DEFAULT '',
        recipe_id TEXT NOT NULL,
        added_at TEXT DEFAULT (datetime('now')),
        PRIMARY KEY(user_id, recipe_id)
    );
    CREATE TABLE IF NOT EXISTS vault.recent (
        user_id TEXT NOT NULL DEFAULT '',
        recipe_id TEXT NOT NULL,
        viewed_at TEXT DEFAULT (datetime('now')),
        PRIMARY KEY(user_id, recipe_id)
    );
    CREATE TABLE IF NOT EXISTS vault.shopping_list (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL DEFAULT '',
        item TEXT NOT NULL,
        recipe_id TEXT,
        recipe_name TEXT DEFAULT '',
        checked INTEGER DEFAULT 0,
        added_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS vault.cooking_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL DEFAULT '',
        recipe_id TEXT NOT NULL,
        cooked_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS vault.recipe_notes (
        user_id TEXT NOT NULL DEFAULT '',
        recipe_id TEXT NOT NULL,
        note TEXT NOT NULL,
        updated_at TEXT DEFAULT (datetime('now')),
        PRIMARY KEY(user_id, recipe_id)
    );
    CREATE TABLE IF NOT EXISTS vault.cooking_state (
        user_id TEXT PRIMARY KEY,
        recipe_id TEXT,
        step INTEGER DEFAULT 0,
        updated_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS vault.recipe_tags (
        user_id TEXT NOT NULL DEFAULT '',
        recipe_id TEXT NOT NULL,
        tag TEXT NOT NULL,
        PRIMARY KEY(user_id, recipe_id, tag)
    );
    -- Recipes a person imported, generated with AI, or translated. Private.
    CREATE TABLE IF NOT EXISTS vault.user_recipes (
        id TEXT PRIMARY KEY,
        owner TEXT NOT NULL,
        name TEXT NOT NULL,
        country TEXT DEFAULT 'Custom',
        lang TEXT DEFAULT 'en',
        collection TEXT DEFAULT 'My Recipes',
        image TEXT DEFAULT '',
        total_time TEXT DEFAULT '',
        yield TEXT DEFAULT '',
        categories TEXT DEFAULT '[]',
        ingredients TEXT NOT NULL,
        steps TEXT NOT NULL,
        nutrition TEXT DEFAULT '{}',
        keywords TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS vault.idx_history_user ON cooking_history(user_id, cooked_at DESC);
    CREATE INDEX IF NOT EXISTS vault.idx_shopping_user ON shopping_list(user_id);
    CREATE INDEX IF NOT EXISTS vault.idx_user_recipes_owner ON user_recipes(owner);
"""

_UNION_VIEW = f"""
    CREATE TEMP VIEW IF NOT EXISTS visible_recipes AS
        SELECT {', '.join(RECIPE_COLUMNS)}, '' AS owner FROM main.recipes
        UNION ALL
        SELECT {', '.join(RECIPE_COLUMNS)}, owner FROM vault.user_recipes;
"""


def init_db():
    """
    Create the vault schema and upgrade an older database, once per process.

    This runs on its own short-lived connection: while a migration is in flight it
    holds a write transaction on both files, and a *serving* connection must never
    do that — other threads attaching the vault at that moment fail with
    "disk I/O error" on some filesystems (seen with a Docker bind mount).
    """
    if _migrated.is_set():
        return
    with _migrate_lock:
        if _migrated.is_set():
            return
        boot = sqlite3.connect(DB_PATH)
        try:
            boot.row_factory = sqlite3.Row
            boot.execute("PRAGMA journal_mode=WAL")
            boot.execute("ATTACH DATABASE ? AS vault", [VAULT_DB_PATH])
            boot.execute("PRAGMA vault.journal_mode=WAL")
            boot.executescript(_VAULT_SCHEMA)
            _migrate(boot)
            boot.commit()
            # Leave both files checkpointed so the first request starts clean.
            boot.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            boot.execute("PRAGMA vault.wal_checkpoint(TRUNCATE)")
        finally:
            boot.close()
        _restrict_permissions()
        _migrated.set()


def _restrict_permissions():
    """
    vault.db holds access-key hashes and everybody's cooking; the default 0644 on
    a shared host or a bind mount lets any local account read it. Best effort —
    some filesystems (a Windows bind mount) simply ignore the mode.
    """
    for path in (VAULT_DB_PATH, f"{VAULT_DB_PATH}-wal", f"{VAULT_DB_PATH}-shm"):
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass


def get_db():
    if not hasattr(local, "db"):
        init_db()
        db = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("ATTACH DATABASE ? AS vault", [VAULT_DB_PATH])
        db.executescript(_UNION_VIEW)
        local.db = db
    return local.db


def _columns(db, table):
    return {r[1] for r in db.execute(f"PRAGMA table_info({table})").fetchall()}


def _table_exists(db, schema, table):
    row = db.execute(
        f"SELECT 1 FROM {schema}.sqlite_master WHERE type='table' AND name=?", [table]
    ).fetchone()
    return row is not None


# Personal tables that older builds kept inside recipes.db.
_LEGACY_TABLES = {
    "favorites": ("recipe_id", "added_at"),
    "recent": ("recipe_id", "viewed_at"),
    "shopping_list": ("item", "recipe_id", "recipe_name", "checked", "added_at"),
    "cooking_history": ("recipe_id", "cooked_at"),
    "recipe_notes": ("recipe_id", "note", "updated_at"),
    "recipe_tags": ("recipe_id", "tag"),
}


def _migrate(db):
    """Move personal data out of recipes.db and into vault.db, once."""
    moved = []
    for table, cols in _LEGACY_TABLES.items():
        if not _table_exists(db, "main", table):
            continue
        present = _columns(db, table)
        usable = [c for c in cols if c in present]
        if not usable:
            # Unrecognised shape — leave it alone rather than risk losing data.
            log.warning(f"legacy table main.{table} has none of {cols}; left in place")
            continue
        rows = db.execute(f"SELECT {', '.join(usable)} FROM main.{table}").fetchall()
        if rows:
            placeholders = ", ".join("?" * (len(usable) + 1))
            db.executemany(
                f"INSERT OR IGNORE INTO vault.{table}(user_id, {', '.join(usable)}) VALUES({placeholders})",
                [[""] + [r[c] for c in usable] for r in rows],
            )
        db.execute(f"DROP TABLE main.{table}")
        moved.append(f"{table}({len(rows)})")

    # cooking_state changed shape (single row keyed by id=1 → one row per user).
    if _table_exists(db, "main", "cooking_state"):
        row = db.execute("SELECT recipe_id, step FROM main.cooking_state LIMIT 1").fetchone()
        if row and row["recipe_id"]:
            db.execute(
                "INSERT OR REPLACE INTO vault.cooking_state(user_id, recipe_id, step) VALUES('', ?, ?)",
                [row["recipe_id"], row["step"]],
            )
        db.execute("DROP TABLE main.cooking_state")
        moved.append("cooking_state")

    # An interim build kept private recipes in recipes.db behind an owner column.
    if _table_exists(db, "main", "recipes") and "owner" in _columns(db, "recipes"):
        owned = db.execute("SELECT * FROM main.recipes WHERE owner != ''").fetchall()
        for r in owned:
            db.execute(
                "INSERT OR IGNORE INTO vault.user_recipes"
                "(id,owner,name,country,lang,collection,image,total_time,yield,categories,"
                "ingredients,steps,nutrition,keywords) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [r["id"], r["owner"], r["name"], r["country"], r["lang"], r["collection"],
                 r["image"], r["total_time"], r["yield"], r["categories"], r["ingredients"],
                 r["steps"], r["nutrition"], r["keywords"]],
            )
            db.execute("DELETE FROM main.recipes_fts WHERE id=?", [r["id"]])
            db.execute("DELETE FROM main.recipes WHERE id=?", [r["id"]])
        if owned:
            moved.append(f"private recipes({len(owned)})")

    db.commit()
    if moved:
        log.info("Moved personal data into vault.db: " + ", ".join(moved))


# ═══ RECIPE LOOKUP ACROSS BOTH DATABASES ═══

def find_recipe(db, rid, uid):
    """
    A recipe from the shared library, or one this vault owns. None otherwise.

    The extra `source` column says which database it came from. `owner` alone is
    ambiguous: in single-user mode a private recipe is owned by '' too, so writes
    routed on `owner` would hit the library table instead of the vault.
    """
    row = db.execute(
        "SELECT *, '' AS owner, 'library' AS source FROM main.recipes WHERE id=?", [rid]
    ).fetchone()
    if row:
        return row
    return db.execute(
        "SELECT *, 'vault' AS source FROM vault.user_recipes WHERE id=? AND owner=?", [rid, uid]
    ).fetchone()


#: Private recipes are few by nature; cap the scan so one vault cannot slow search.
USER_RECIPE_SCAN_LIMIT = 500


def search_user_recipes(db, uid, query="", country="", lang="", collection="",
                        favorites=False, tag=""):
    """
    Substring search over one vault's private recipes.

    They never enter the library's FTS index (that would put personal data in the
    shareable file), and there are only ever a handful, so LIKE is plenty.
    `uid` may be '' — that is the single-user / legacy vault, not "no vault".
    """
    wheres, args = ["owner=?"], [uid]
    if query:
        # Escape LIKE wildcards so searching for "50%" is a search, not a match-all.
        escaped = re.sub(r"([%_\\])", r"\\\1", query.strip().lower())
        needle = f"%{escaped}%"
        wheres.append("(lower(name) LIKE ? ESCAPE '\\' OR lower(ingredients) LIKE ? ESCAPE '\\'"
                      " OR lower(keywords) LIKE ? ESCAPE '\\')")
        args += [needle, needle, needle]
    if country:
        wheres.append("country=?"); args.append(country)
    if lang:
        wheres.append("lang=?"); args.append(lang)
    if collection:
        wheres.append("collection=?"); args.append(collection)
    if favorites:
        wheres.append("id IN (SELECT recipe_id FROM vault.favorites WHERE user_id=?)"); args.append(uid)
    if tag:
        wheres.append("id IN (SELECT recipe_id FROM vault.recipe_tags WHERE user_id=? AND tag=?)")
        args += [uid, tag]
    return db.execute(
        f"SELECT * FROM vault.user_recipes WHERE {' AND '.join(wheres)}"
        " ORDER BY created_at DESC LIMIT ?", args + [USER_RECIPE_SCAN_LIMIT]
    ).fetchall()


# recipes_fts is an FTS5 *external content* table (content='recipes'). Rows must be
# removed with the special 'delete' command carrying the old values, and re-inserted
# with the content rowid — a bare INSERT/DELETE corrupts the index and makes every
# later MATCH raise "missing row N from content table".
_FTS_COLS = ("id", "name", "ingredients", "keywords", "collection", "categories")


def _fts_row(db, rid):
    return db.execute(
        f"SELECT rowid, {', '.join(_FTS_COLS)} FROM main.recipes WHERE id=?", [rid]
    ).fetchone()


def fts_unindex(db, rid):
    """Drop a library recipe from the search index. Call *before* changing its row."""
    row = _fts_row(db, rid)
    if not row:
        return
    db.execute(
        f"INSERT INTO recipes_fts(recipes_fts, rowid, {', '.join(_FTS_COLS)})"
        f" VALUES('delete', ?, {', '.join('?' * len(_FTS_COLS))})",
        [row["rowid"]] + [row[c] for c in _FTS_COLS],
    )


def fts_index(db, rid):
    """Index a library recipe. Call *after* its row is written."""
    row = _fts_row(db, rid)
    if not row:
        return
    db.execute(
        f"INSERT INTO recipes_fts(rowid, {', '.join(_FTS_COLS)})"
        f" VALUES(?, {', '.join('?' * len(_FTS_COLS))})",
        [row["rowid"]] + [row[c] for c in _FTS_COLS],
    )


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
        "stepCount":len(json_col(row["steps"], [])),
        "hasNote": row["id"] in noted_ids if noted_ids is not None else False,
    }

def slim_rows(rows, uid=""):
    """Convert rows to slim dicts, with one batched note lookup for this vault."""
    if not rows:
        return []
    db = get_db()
    ids = [r["id"] for r in rows]
    placeholders = ",".join("?" * len(ids))
    noted = set(r[0] for r in db.execute(
        f"SELECT recipe_id FROM vault.recipe_notes WHERE user_id=? AND recipe_id IN ({placeholders})",
        [uid] + ids).fetchall())
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
    ingredients = json_col(row["ingredients"], [])
    ing_icons = []
    for ing in ingredients:
        icon_id = _get_ingredient_icon(ing)
        ing_icons.append(f"{ICON_BASE}{icon_id}" if icon_id else None)
    return {
        "id":row["id"],"name":row["name"],"country":row["country"],
        "lang":row["lang"],"collection":row["collection"],"image":row["image"],
        "totalTime":row["total_time"],"yield":row["yield"],
        "categories":json_col(row["categories"], []),
        "ingredients":ingredients,
        "ingredient_icons":ing_icons,
        "steps":json_col(row["steps"], []),
        "nutrition":json_col(row["nutrition"], {}),
        "keywords":row["keywords"],
    }
