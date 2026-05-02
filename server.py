#!/usr/bin/env python3
"""MixVault - SQLite-backed server with FTS5 search."""
import json, sqlite3, threading, os, hashlib, time, re, signal, sys, logging, shutil
from http.server import HTTPServer, SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote
import urllib.request

# ═══ LOGGING ═══
LOG_DIR = Path(os.environ.get("LOG_DIR", str(Path(__file__).parent / "data" / "logs")))
LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "server.log"),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger("cooker")

# Load .env
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            if v.strip():
                os.environ[k.strip()] = v.strip()

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "")  # e.g. http://localhost:11434
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free")
# LLM_PROVIDER: comma-separated priority order. Options: ollama, groq, openrouter
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "groq,openrouter,ollama")
AUTH_PIN = os.environ.get("AUTH_PIN", "")
if OLLAMA_URL: log.info(f"Ollama configured ({OLLAMA_URL}, model={OLLAMA_MODEL})")
if GROQ_API_KEY: log.info(f"Groq API key loaded ({GROQ_API_KEY[:8]}...)")
if OPENROUTER_API_KEY: log.info(f"OpenRouter API key loaded ({OPENROUTER_API_KEY[:12]}...)")
if AUTH_PIN: log.info("PIN authentication enabled")
log.info(f"LLM priority: {LLM_PROVIDER}")

def _mymemory_translate(text, src, tgt):
    """Fallback translator using MyMemory API."""
    params = urllib.parse.urlencode({'q': text, 'langpair': f'{src}|{tgt}'})
    req = urllib.request.Request(
        f'https://api.mymemory.translated.net/get?{params}',
        headers={'User-Agent': 'Mozilla/5.0'})
    resp = urllib.request.urlopen(req, timeout=15)
    data = json.loads(resp.read())
    translated = data.get('responseData', {}).get('translatedText', '')
    if not translated or data.get('responseStatus') != 200:
        raise Exception(f"MyMemory failed: {data.get('responseStatus')}")
    return translated

def _gtranslate(text, src, tgt):
    """Translate with Google→MyMemory fallback and retry/backoff."""
    if not text or not text.strip():
        return text
    # Try Google first with retry
    for attempt in range(3):
        try:
            params = urllib.parse.urlencode({'client':'gtx','sl':src,'tl':tgt,'dt':'t','q':text})
            req = urllib.request.Request(
                f'https://translate.googleapis.com/translate_a/single?{params}',
                headers={'User-Agent':'Mozilla/5.0'})
            resp = urllib.request.urlopen(req, timeout=15)
            data = json.loads(resp.read())
            return ''.join(s[0] for s in data[0])
        except Exception:
            if attempt < 2:
                time.sleep(0.5 * (attempt + 1))
    # Fallback to MyMemory
    return _mymemory_translate(text, src, tgt)

PORT = 8080
MAX_BODY_SIZE = 64 * 1024  # 64KB max POST body
START_TIME = time.time()

# Rate limiting for AI endpoint
_ai_rate = {}  # ip -> (count, window_start)
AI_RATE_LIMIT = 10  # requests per minute
AI_RATE_WINDOW = 60  # seconds

# Meta cache
_meta_cache = {"data": None, "ts": 0}
META_CACHE_TTL = 30  # seconds

def _ai_chat(messages, max_tokens=1024):
    """Call AI using provider priority from LLM_PROVIDER env var."""
    providers = []
    for p in LLM_PROVIDER.split(","):
        p = p.strip().lower()
        if p == "ollama" and OLLAMA_URL:
            providers.append(("ollama", f"{OLLAMA_URL.rstrip('/')}/api/chat", "", OLLAMA_MODEL, {}))
        elif p == "groq" and GROQ_API_KEY:
            providers.append(("groq", "https://api.groq.com/openai/v1/chat/completions", GROQ_API_KEY, GROQ_MODEL, {}))
        elif p == "openrouter" and OPENROUTER_API_KEY:
            providers.append(("openrouter", "https://openrouter.ai/api/v1/chat/completions", OPENROUTER_API_KEY, OPENROUTER_MODEL, {"HTTP-Referer": "http://localhost:8080"}))
    if not providers:
        return None
    for name, url, key, model, extra_headers in providers:
        try:
            if name == "ollama":
                # Ollama uses different API format
                body = json.dumps({"model": model, "messages": messages, "stream": False}).encode()
                headers = {"Content-Type": "application/json"}
            else:
                body = json.dumps({"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": 0.7}).encode()
                headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json", "User-Agent": "MixVault/1.0"}
                headers.update(extra_headers)
            req = urllib.request.Request(url, data=body, headers=headers)
            resp = urllib.request.urlopen(req, timeout=60 if name == "ollama" else 30)
            data = json.loads(resp.read())
            if name == "ollama":
                return data["message"]["content"]
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            log.warning(f"AI provider {name} failed: {e}")
            continue
    return None
DB_PATH = os.environ.get("DB_PATH", str(Path(__file__).parent / "data" / "recipes.db"))
STATIC = str(Path(__file__).parent / "static")
BACKUP_DIR = Path(os.environ.get("BACKUP_DIR", str(Path(__file__).parent / "data" / "backups")))
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

LANG_NAMES = {
    "en":"English","de":"German","fr":"French","it":"Italian","es":"Spanish",
    "pt":"Portuguese","pl":"Polish","cs":"Czech","ro":"Romanian","nl":"Dutch",
    "da":"Danish","sv":"Swedish","no":"Norwegian","hu":"Hungarian","tr":"Turkish",
    "el":"Greek","zh":"Chinese","id":"Indonesian","ms":"Malay","is":"Icelandic",
    "ar":"Arabic","vi":"Vietnamese",
}

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


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=STATIC, **kw)

    def do_GET(self):
        p = urlparse(self.path)
        routes = {
            "/api/recipes": self._search,
            "/api/meta": self._meta,
            "/api/favorites": self._favorites_list,
            "/api/shopping": self._shopping_list,
            "/api/history": self._history_list,
        }
        if p.path in routes:
            routes[p.path](parse_qs(p.query))
        elif p.path.startswith("/api/similar/"):
            self._similar(unquote(p.path[13:]), parse_qs(p.query))
        elif p.path.startswith("/api/recipe/"):
            self._recipe(unquote(p.path[12:]))
        elif p.path.startswith("/api/note/"):
            self._note_get(unquote(p.path[10:]))
        else:
            super().do_GET()

    def do_POST(self):
        p = urlparse(self.path)
        content_len = int(self.headers.get("Content-Length", 0))
        if content_len > MAX_BODY_SIZE:
            self.send_error(413, "Request body too large")
            return
        body = self.rfile.read(content_len)
        try:
            req = json.loads(body) if body else {}
        except Exception:
            req = {}
        if p.path.startswith("/api/favorite/"):
            self._favorite_toggle(unquote(p.path[14:]))
        elif p.path.startswith("/api/translate/"):
            self._translate(unquote(p.path[15:]), req)
        elif p.path == "/api/shopping/add":
            self._shopping_add(req)
        elif p.path == "/api/shopping/toggle":
            self._shopping_toggle(req)
        elif p.path == "/api/shopping/clear":
            self._shopping_clear(req)
        elif p.path == "/api/shopping/restore":
            self._shopping_restore(req)
        elif p.path == "/api/shopping/delete":
            self._shopping_delete(req)
        elif p.path.startswith("/api/note/"):
            self._note_save(unquote(p.path[10:]), req)
        elif p.path.startswith("/api/cooked/"):
            self._mark_cooked(unquote(p.path[12:]))
        elif p.path == "/api/ai":
            self._ai(req)
        else:
            self.send_error(404)

    def _json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",len(body))
        origin = self.headers.get("Origin", "")
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Credentials", "true")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        """Handle CORS preflight."""
        self.send_response(204)
        origin = self.headers.get("Origin", "")
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Allow-Credentials", "true")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _search(self, params):
        db = get_db()
        q = params.get("q",[""])[0].strip()
        country = params.get("country",[""])[0]
        lang = params.get("lang",[""])[0]
        col = params.get("collection",[""])[0]
        fav = params.get("favorites",[""])[0]
        random = params.get("random",[""])[0]
        limit = min(int(params.get("limit",["60"])[0]), 200)
        offset = int(params.get("offset",["0"])[0])

        wheres, args = [], []
        if country:
            wheres.append("r.country=?"); args.append(country)
        if lang:
            wheres.append("r.lang=?"); args.append(lang)
        if col:
            wheres.append("r.collection=?"); args.append(col)
        if fav == "1":
            wheres.append("r.id IN (SELECT recipe_id FROM favorites)")

        if random == "1":
            where_sql = " WHERE "+" AND ".join(wheres) if wheres else ""
            count = 1
            rows = db.execute(f"SELECT * FROM recipes r{where_sql} ORDER BY RANDOM() LIMIT 1", args).fetchall()
        elif q:
            # FTS search — escape special chars and add prefix matching
            fts_q = _fts_escape(q)
            if not fts_q:
                count = 0; rows = []
            elif wheres:
                where_sql = " AND ".join(wheres)
                count = db.execute(f"SELECT count(*) FROM recipes r JOIN recipes_fts f ON r.id=f.id WHERE recipes_fts MATCH ? AND {where_sql}", [fts_q]+args).fetchone()[0]
                rows = db.execute(f"SELECT r.* FROM recipes r JOIN recipes_fts f ON r.id=f.id WHERE recipes_fts MATCH ? AND {where_sql} ORDER BY rank LIMIT ? OFFSET ?", [fts_q]+args+[limit,offset]).fetchall()
            else:
                count = db.execute("SELECT count(*) FROM recipes r JOIN recipes_fts f ON r.id=f.id WHERE recipes_fts MATCH ?", [fts_q]).fetchone()[0]
                rows = db.execute("SELECT r.* FROM recipes r JOIN recipes_fts f ON r.id=f.id WHERE recipes_fts MATCH ? ORDER BY rank LIMIT ? OFFSET ?", [fts_q,limit,offset]).fetchall()
        else:
            where_sql = " WHERE "+" AND ".join(wheres) if wheres else ""
            count = db.execute(f"SELECT count(*) FROM recipes r{where_sql}", args).fetchone()[0]
            rows = db.execute(f"SELECT * FROM recipes r{where_sql} LIMIT ? OFFSET ?", args+[limit,offset]).fetchall()

        self._json({"total":count,"offset":offset,"limit":limit,"recipes":slim_rows(rows)})

    def _recipe(self, rid):
        db = get_db()
        row = db.execute("SELECT * FROM recipes WHERE id=?", [rid]).fetchone()
        if row:
            # Track recent view
            db.execute("INSERT OR REPLACE INTO recent(recipe_id) VALUES(?)", [rid])
            db.commit()
            data = full_row(row)
            data["is_favorite"] = db.execute("SELECT 1 FROM favorites WHERE recipe_id=?", [rid]).fetchone() is not None
            note_row = db.execute("SELECT note FROM recipe_notes WHERE recipe_id=?", [rid]).fetchone()
            data["note"] = note_row["note"] if note_row else ""
            cook_count = db.execute("SELECT count(*) FROM cooking_history WHERE recipe_id=?", [rid]).fetchone()[0]
            data["cook_count"] = cook_count
            self._json(data)
        else:
            self._json({"error":"not found"}, 404)

    def _meta(self, params=None):
        now = time.time()
        if _meta_cache["data"] and now - _meta_cache["ts"] < META_CACHE_TTL:
            return self._json(_meta_cache["data"])
        db = get_db()
        total = db.execute("SELECT count(*) FROM recipes").fetchone()[0]
        countries = [{"country":r[0],"lang":r[1],"count":r[2]}
            for r in db.execute("SELECT country, lang, count(*) FROM recipes GROUP BY country ORDER BY count(*) DESC")]
        lang_rows = db.execute("SELECT lang, count(*) FROM recipes GROUP BY lang ORDER BY count(*) DESC").fetchall()
        languages = [{"lang":r[0],"name":LANG_NAMES.get(r[0],r[0]),"count":r[1]} for r in lang_rows]
        fav_count = db.execute("SELECT count(*) FROM favorites").fetchone()[0]
        result = {"total":total,"countries":countries,"languages":languages,"favorites":fav_count}
        _meta_cache["data"] = result
        _meta_cache["ts"] = now
        self._json(result)

    def _favorite_toggle(self, rid):
        db = get_db()
        exists = db.execute("SELECT 1 FROM favorites WHERE recipe_id=?", [rid]).fetchone()
        if exists:
            db.execute("DELETE FROM favorites WHERE recipe_id=?", [rid])
            db.commit()
            self._json({"favorited":False})
        else:
            db.execute("INSERT OR IGNORE INTO favorites(recipe_id) VALUES(?)", [rid])
            db.commit()
            self._json({"favorited":True})

    def _similar(self, rid, params):
        db = get_db()
        limit = min(int(params.get("limit", ["6"])[0]), 20)
        row = db.execute("SELECT ingredients, lang FROM recipes WHERE id=?", [rid]).fetchone()
        if not row:
            self._json({"recipes": []})
            return
        ings = json.loads(row["ingredients"])[:3]
        # Build FTS query from first 3 ingredients (extract key words)
        terms = []
        for ing in ings:
            words = [w for w in ing.split() if len(w) > 3 and not w.replace(',','').isdigit()]
            if words:
                terms.append(words[-1])  # last word is usually the ingredient name
        if not terms:
            self._json({"recipes": []})
            return
        fts_q = " OR ".join('"' + ''.join(c for c in t if c.isalnum() or c in '-_') + '"*' for t in terms[:3])
        rows = db.execute(
            "SELECT r.* FROM recipes r JOIN recipes_fts f ON r.id=f.id "
            "WHERE recipes_fts MATCH ? AND r.lang=? AND r.id!=? ORDER BY rank LIMIT ?",
            [fts_q, row["lang"], rid, limit * 3]
        ).fetchall()
        # Deduplicate by name
        seen = set()
        unique = []
        for r in rows:
            if r["name"] not in seen:
                seen.add(r["name"])
                unique.append(r)
                if len(unique) >= limit:
                    break
        self._json({"recipes": slim_rows(unique)})

    def _favorites_list(self, params):
        db = get_db()
        rows = db.execute("""
            SELECT r.* FROM recipes r
            JOIN favorites f ON r.id=f.recipe_id
            ORDER BY f.added_at DESC
        """).fetchall()
        self._json({"total":len(rows),"offset":0,"limit":len(rows),"recipes":slim_rows(rows)})

    def _translate(self, rid, req):
        tgt = req.get("lang", "en")
        db = get_db()
        row = db.execute("SELECT * FROM recipes WHERE id=?", [rid]).fetchone()
        if not row:
            return self._json({"error": "not found"}, 404)
        src = row["lang"]
        if src == tgt:
            return self._json({"error": "same language", "id": rid})
        # Check if translation already exists
        new_id = hashlib.md5(f"{rid}:{tgt}".encode()).hexdigest()[:12]
        existing = db.execute("SELECT id FROM recipes WHERE id=?", [new_id]).fetchone()
        if existing:
            return self._json({"id": new_id, "cached": True})
        # Translate fields
        try:
            name = _gtranslate(row["name"], src, tgt)
            ings = [_gtranslate(i, src, tgt) for i in json.loads(row["ingredients"])]
            steps = [_gtranslate(s, src, tgt) for s in json.loads(row["steps"])]
            yld = _gtranslate(row["yield"], src, tgt) if row["yield"] else ""
            cats = [_gtranslate(c, src, tgt) for c in json.loads(row["categories"])]
            kw = _gtranslate(row["keywords"], src, tgt) if row["keywords"] else ""
        except Exception as e:
            return self._json({"error": f"translation failed: {e}"}, 500)
        # Insert as new recipe
        db.execute(
            "INSERT OR IGNORE INTO recipes(id,name,country,lang,collection,image,total_time,yield,categories,ingredients,steps,nutrition,keywords) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (new_id, name, row["country"], tgt,
             row["collection"], row["image"], row["total_time"], yld,
             json.dumps(cats, ensure_ascii=False),
             json.dumps(ings, ensure_ascii=False),
             json.dumps(steps, ensure_ascii=False),
             row["nutrition"], kw)
        )
        # Update FTS
        db.execute(
            "INSERT INTO recipes_fts(id,name,ingredients,keywords,collection,categories) VALUES(?,?,?,?,?,?)",
            (new_id, name, json.dumps(ings, ensure_ascii=False), kw, row["collection"],
             json.dumps(cats, ensure_ascii=False))
        )
        db.commit()
        self._json({"id": new_id, "cached": False})

    # --- Shopping list ---
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
        self._shopping_list()

    def _shopping_toggle(self, req):
        db = get_db()
        sid = req.get("id")
        if sid:
            db.execute("UPDATE shopping_list SET checked=NOT checked WHERE id=?", [sid])
            db.commit()
        self._shopping_list()

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
        self._shopping_list()

    def _shopping_delete(self, req):
        db = get_db()
        sid = req.get("id")
        if sid:
            db.execute("DELETE FROM shopping_list WHERE id=?", [sid])
            db.commit()
        self._shopping_list()

    # --- Cooking history ---
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

    # --- Delete recipe ---
    def _recipe_delete(self, rid):
        db = get_db()
        db.execute("DELETE FROM recipes_fts WHERE id=?", [rid])
        db.execute("DELETE FROM recipes WHERE id=?", [rid])
        db.execute("DELETE FROM favorites WHERE recipe_id=?", [rid])
        db.execute("DELETE FROM recipe_notes WHERE recipe_id=?", [rid])
        db.execute("INSERT INTO recipes_fts(recipes_fts) VALUES('rebuild')")
        db.commit()
        _meta_cache["ts"] = 0
        self._json({"ok": True})

    # --- Edit recipe ---
    def _recipe_edit(self, rid, req):
        db = get_db()
        row = db.execute("SELECT * FROM recipes WHERE id=?", [rid]).fetchone()
        if not row:
            return self._json({"error": "not found"}, 404)
        name = req.get("name", row["name"])
        ingredients = req.get("ingredients") or json.loads(row["ingredients"])
        steps = req.get("steps") or json.loads(row["steps"])
        image = req.get("image", row["image"])
        yld = req.get("yield", row["yield"])
        total_time = req.get("totalTime", row["total_time"])
        categories = req.get("categories") or json.loads(row["categories"])
        keywords = req.get("keywords", row["keywords"])
        db.execute(
            "UPDATE recipes SET name=?,image=?,total_time=?,yield=?,categories=?,ingredients=?,steps=?,keywords=? WHERE id=?",
            [name, image, total_time, yld, json.dumps(categories, ensure_ascii=False),
             json.dumps(ingredients, ensure_ascii=False), json.dumps(steps, ensure_ascii=False), keywords, rid])
        db.execute("DELETE FROM recipes_fts WHERE id=?", [rid])
        db.execute("INSERT INTO recipes_fts(id,name,ingredients,keywords,collection,categories) VALUES(?,?,?,?,?,?)",
            (rid, name, json.dumps(ingredients, ensure_ascii=False), keywords, row["collection"],
             json.dumps(categories, ensure_ascii=False)))
        db.commit()
        self._json({"ok": True})

    # --- Cooking state (cross-device resume) ---
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

    # --- Notes ---
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

    # --- AI ---
    def _ai(self, req):
        # Rate limiting
        ip = self.client_address[0]
        now = time.time()
        count, window_start = _ai_rate.get(ip, (0, now))
        if now - window_start > AI_RATE_WINDOW:
            count, window_start = 0, now
        if count >= AI_RATE_LIMIT:
            return self._json({"error": "Rate limited. Try again in a minute."}, 429)
        _ai_rate[ip] = (count + 1, window_start)

        prompt = req.get("prompt", "")
        recipe_context = req.get("context", "")
        if not prompt:
            return self._json({"error": "no prompt"}, 400)
        # AI-powered search: extract keywords from natural language, search DB
        messages = [
            {"role": "system", "content": """You are a recipe search assistant for a Thermomix recipe database with 80,000 recipes in many languages (en, de, fr, es, it, pt, ro, pl, cs, nl, da, sv, no, hu, tr, el, zh, id, ms, is, ar, vi).
The user describes what they want to cook or what ingredients they have.
Your job: extract search keywords in MULTIPLE languages to maximize results.
Reply ONLY with a JSON object: {"searches": [{"keywords": ["word1", "word2"], "lang": "en"}, {"keywords": ["wort1", "wort2"], "lang": "de"}]}
- Each search has keywords (ingredient names, dish types) translated to that language
- Include 2-4 most relevant languages based on the user's question and common cuisines
- Keep keywords short (single words, food terms)
No explanation, just the JSON."""},
            {"role": "user", "content": prompt}
        ]
        if recipe_context:
            messages[0]["content"] += f"\n\nAdditional context:\n{recipe_context}"
        result = _ai_chat(messages, max_tokens=100)
        if result is None:
            has_keys = bool(GROQ_API_KEY or OPENROUTER_API_KEY)
            msg = "AI providers failed (check API keys or rate limits)" if has_keys else "No AI API keys configured. Add GROQ_API_KEY or OPENROUTER_API_KEY to .env"
            return self._json({"error": msg}, 503)
        # Parse AI response to get keywords
        try:
            m = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', result)
            if m:
                parsed = json.loads(m.group())
                searches = parsed.get("searches", [])
                if not searches and "keywords" in parsed:
                    searches = [{"keywords": parsed["keywords"], "lang": parsed.get("lang", "")}]
            else:
                searches = [{"keywords": result.split()[:5], "lang": ""}]
        except Exception:
            searches = [{"keywords": result.split()[:5], "lang": ""}]
        # Search DB with extracted keywords across languages
        db = get_db()
        all_recipes = []
        seen_names = set()
        all_keywords = []
        all_langs = []
        for s in searches:
            kws = s.get("keywords", [])
            lang = s.get("lang", "")
            if not kws: continue
            all_keywords.extend(kws)
            if lang: all_langs.append(lang)
            fts_q = " OR ".join('"' + ''.join(c for c in w if c.isalnum() or c in '-_') + '"*' for w in kws if w)
            try:
                args = [fts_q]
                where_extra = ""
                if lang:
                    where_extra = " AND r.lang=?"
                    args.append(lang)
                rows = db.execute(
                    f"SELECT r.* FROM recipes r JOIN recipes_fts f ON r.id=f.id WHERE recipes_fts MATCH ?{where_extra} ORDER BY rank LIMIT 10",
                    args).fetchall()
                for r in rows:
                    key = r["name"].lower()
                    if key not in seen_names:
                        seen_names.add(key)
                        all_recipes.append(r)
            except Exception:
                pass
        # Batch convert at end
        noted = set()
        if all_recipes:
            ids = [r["id"] for r in all_recipes]
            ph = ",".join("?" * len(ids))
            noted = set(x[0] for x in db.execute(f"SELECT recipe_id FROM recipe_notes WHERE recipe_id IN ({ph})", ids).fetchall())
        self._json({"keywords": all_keywords, "langs": all_langs, "total": len(all_recipes),
                     "recipes": [slim_row(r, noted) for r in all_recipes[:20]]})

    # ═══ AI RECIPE CREATOR ═══
    def _ai_create(self, req):
        """Multi-turn chat for recipe creation."""
        messages = req.get("messages", [])
        if not messages:
            return self._json({"error": "no messages"}, 400)
        
        system = """You are a creative chef assistant. Help the user create a recipe.
- Ask about preferences, dietary restrictions, available ingredients
- Suggest alternatives when asked
- Be conversational and friendly, speak the same language as the user
- NEVER mention JSON, code, format, or technical details to the user
- When generating recipes, include DETAILED steps with:
  - Exact temperatures (e.g., "180°C", "350°F")
  - Cooking times for each step
  - Oven position (top/middle/bottom rack) when relevant
  - Pan/pot sizes and types
  - Visual cues (e.g., "until golden brown", "until a toothpick comes out clean")
  - Resting times
- When the user says they're happy/satisfied/done/let's do it/save it/perfect/da/gata/ok, include the recipe data at the VERY END of your message in a hidden block like this (the user won't see it):
```json
{"name":"Recipe Name","ingredients":["200 g ingredient",...],"steps":["Step 1 with temperature and time...",...],"yield":"4 servings","totalTime":"PT45M","categories":["Dessert"],"keywords":"keyword1, keyword2","lang":"ro"}
```
- The JSON must be valid. Use the language the user is speaking for the recipe content.
- Steps must be detailed and complete — a beginner should be able to follow them.
- Before outputting JSON, give a nice summary like "Perfect! Here's your recipe:" and list the key details naturally.
- Only output the JSON when the user clearly confirms they want this recipe."""
        
        full_messages = [{"role": "system", "content": system}] + messages
        result = _ai_chat(full_messages, max_tokens=1024)
        if result is None:
            return self._json({"error": "AI unavailable"}, 503)
        
        # Check if response contains a final recipe JSON
        recipe_json = None
        m = re.search(r'```json\s*(\{.*?\})\s*```', result, re.DOTALL)
        if m:
            try:
                recipe_json = json.loads(m.group(1))
            except:
                pass
        
        self._json({"reply": result, "recipe": recipe_json})

    def _ai_image_search(self, req):
        """Find images for a recipe - search DB or Unsplash."""
        query = req.get("query", "")
        if not query:
            return self._json({"error": "no query"}, 400)
        
        images = []
        # 1. Search DB for similar recipe images by name
        db = get_db()
        stop = {'de','la','cu','si','in','din','pe','un','o','a','the','and','with','for','of','le','du','des','et','con','del','di','e','y','el','los','las','mit','und','für'}
        words = [w.strip() for w in query.split() if len(w.strip()) > 2 and w.strip().lower() not in stop]
        if not words:
            return self._json({"images": []})
        # Search by LIKE on name for relevance
        seen = set()
        # Try name LIKE with all key words
        like_clauses = " AND ".join(f"r.name LIKE ?" for _ in words)
        like_args = [f"%{w}%" for w in words]
        rows = db.execute(
            f"SELECT r.name, r.image FROM recipes r WHERE {like_clauses} AND r.image != '' LIMIT 8",
            like_args).fetchall()
        for r in rows:
            if r["image"] not in seen:
                seen.add(r["image"])
                images.append({"url": r["image"], "source": "database", "title": r["name"]})
        # If not enough, try individual words
        if len(images) < 4:
            for w in words:
                rows2 = db.execute(
                    "SELECT r.name, r.image FROM recipes r WHERE r.name LIKE ? AND r.image != '' LIMIT 4",
                    [f"%{w}%"]).fetchall()
                for r in rows2:
                    if r["image"] not in seen:
                        seen.add(r["image"])
                        images.append({"url": r["image"], "source": "database", "title": r["name"]})
                    if len(images) >= 8:
                        break
        
        # 2. Try Unsplash source (no API key needed)
        try:
            params = urllib.parse.urlencode({"query": query, "per_page": "4", "content_filter": "high"})
            req_url = f"https://unsplash.com/napi/search/photos?{params}"
            ureq = urllib.request.Request(req_url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
            resp = urllib.request.urlopen(ureq, timeout=5)
            data = json.loads(resp.read())
            for photo in data.get("results", [])[:4]:
                images.append({
                    "url": photo["urls"]["regular"],
                    "thumb": photo["urls"]["small"],
                    "source": "unsplash",
                    "title": photo.get("alt_description", ""),
                    "credit": photo["user"]["name"],
                })
        except:
            pass
        
        self._json({"images": images})

    # ═══ COOKIDOO URL IMPORT ═══
    def _cookidoo_import(self, req):
        """Scrape Cookidoo URL for public data, AI-generate steps, save."""
        url = req.get("url", "").strip()
        if not url or "cookidoo" not in url:
            return self._json({"error": "Invalid Cookidoo URL"}, 400)
        # Scrape public data
        try:
            ureq = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            html = urllib.request.urlopen(ureq, timeout=15).read().decode()
        except Exception as e:
            return self._json({"error": f"Failed to fetch: {e}"}, 500)
        import html as html_mod
        m = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL)
        if not m:
            return self._json({"error": "No recipe data found on page"}, 404)
        try:
            data = json.loads(m.group(1))
        except:
            return self._json({"error": "Failed to parse recipe data"}, 500)
        name = html_mod.unescape(data.get("name", ""))
        ingredients = [html_mod.unescape(i) for i in data.get("recipeIngredient", [])]
        image = data.get("image", "")
        total_time = data.get("totalTime", "")
        yld = data.get("recipeYield", "")
        nutrition = data.get("nutrition", {})
        categories = data.get("recipeCategory", [])
        keywords = data.get("keywords", "")
        lang = data.get("inLanguage", "en")[:2]
        if not name or not ingredients:
            return self._json({"error": "Recipe has no name or ingredients"}, 400)
        # Check if already exists
        db = get_db()
        existing = db.execute("SELECT id FROM recipes WHERE name=? AND lang=?", [name, lang]).fetchone()
        if existing:
            return self._json({"id": existing[0], "exists": True, "name": name})
        # AI-generate steps
        steps = []
        ing_text = "\n".join(f"- {i}" for i in ingredients)
        messages = [
            {"role": "system", "content": f"You are a chef. Generate detailed cooking steps for this recipe. Include temperatures, times, and visual cues. Output ONLY a JSON array of step strings. Language: {lang}"},
            {"role": "user", "content": f"Recipe: {name}\nYield: {yld}\nTime: {total_time}\nIngredients:\n{ing_text}"}
        ]
        ai_result = _ai_chat(messages, max_tokens=1024)
        if ai_result:
            try:
                # Extract JSON array from response
                arr_m = re.search(r'\[.*\]', ai_result, re.DOTALL)
                if arr_m:
                    steps = json.loads(arr_m.group())
            except:
                steps = [s.strip() for s in ai_result.split("\n") if s.strip() and not s.strip().startswith("{")]
        if not steps:
            steps = ["Follow standard preparation method for this recipe."]
        # Save
        rid = hashlib.md5(f"{name}:{lang}".encode()).hexdigest()[:12]
        nut = {"calories": nutrition.get("calories",""), "protein": nutrition.get("proteinContent",""),
               "carbs": nutrition.get("carbohydrateContent",""), "fat": nutrition.get("fatContent","")}
        db.execute(
            "INSERT OR IGNORE INTO recipes(id,name,country,lang,collection,image,total_time,yield,categories,ingredients,steps,nutrition,keywords) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (rid, name, "Imported", lang, "Cookidoo Import", image, total_time, yld,
             json.dumps(categories, ensure_ascii=False), json.dumps(ingredients, ensure_ascii=False),
             json.dumps(steps, ensure_ascii=False), json.dumps(nut, ensure_ascii=False), keywords))
        db.execute("INSERT OR IGNORE INTO recipes_fts(id,name,ingredients,keywords,collection,categories) VALUES(?,?,?,?,?,?)",
            (rid, name, json.dumps(ingredients, ensure_ascii=False), keywords, "Cookidoo Import", json.dumps(categories, ensure_ascii=False)))
        db.commit()
        _meta_cache["ts"] = 0
        self._json({"id": rid, "exists": False, "name": name, "steps_generated": len(steps)})

    # ═══ SHARE RECIPE ═══
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

    # ═══ NUTRITIONAL GOALS FILTER ═══
    def _nutrition_search(self, params):
        """Filter recipes by nutritional values."""
        db = get_db()
        max_cal = params.get("max_calories", [""])[0]
        min_protein = params.get("min_protein", [""])[0]
        max_carbs = params.get("max_carbs", [""])[0]
        max_fat = params.get("max_fat", [""])[0]
        lang = params.get("lang", [""])[0]
        limit = min(int(params.get("limit", ["30"])[0]), 100)
        # SQLite JSON extraction on nutrition field
        wheres = ["json_extract(r.nutrition, '$.calories') != ''"]
        args = []
        if max_cal:
            wheres.append("CAST(REPLACE(json_extract(r.nutrition, '$.calories'), ' kcal', '') AS REAL) <= ?")
            args.append(float(max_cal))
        if min_protein:
            wheres.append("CAST(REPLACE(REPLACE(json_extract(r.nutrition, '$.protein'), ' g', ''), ',', '.') AS REAL) >= ?")
            args.append(float(min_protein))
        if max_carbs:
            wheres.append("CAST(REPLACE(REPLACE(json_extract(r.nutrition, '$.carbs'), ' g', ''), ',', '.') AS REAL) <= ?")
            args.append(float(max_carbs))
        if max_fat:
            wheres.append("CAST(REPLACE(REPLACE(json_extract(r.nutrition, '$.fat'), ' g', ''), ',', '.') AS REAL) <= ?")
            args.append(float(max_fat))
        if lang:
            wheres.append("r.lang=?")
            args.append(lang)
        where_sql = " AND ".join(wheres)
        rows = db.execute(f"SELECT r.* FROM recipes r WHERE {where_sql} LIMIT ?", args + [limit]).fetchall()
        self._json({"total": len(rows), "recipes": slim_rows(rows)})

    # ═══ SUBSTITUTION SUGGESTIONS ═══
    def _substitutions(self, req):
        """AI-powered ingredient substitution suggestions."""
        ingredient = req.get("ingredient", "").strip()
        context = req.get("context", "")  # recipe name or dietary need
        if not ingredient:
            return self._json({"error": "no ingredient"}, 400)
        messages = [
            {"role": "system", "content": "You are a cooking expert. Suggest 3-5 substitutions for the given ingredient. Consider flavor, texture, and cooking properties. Reply ONLY with a JSON array: [{\"sub\":\"substitute name\",\"ratio\":\"conversion ratio\",\"note\":\"brief note\"}]"},
            {"role": "user", "content": f"Ingredient: {ingredient}" + (f"\nRecipe context: {context}" if context else "")}
        ]
        result = _ai_chat(messages, max_tokens=300)
        if not result:
            return self._json({"error": "AI unavailable"}, 503)
        try:
            arr_m = re.search(r'\[.*\]', result, re.DOTALL)
            subs = json.loads(arr_m.group()) if arr_m else []
        except:
            subs = []
        self._json({"ingredient": ingredient, "substitutions": subs})

    def log_message(self, fmt, *args):
        log.info(f"{self.client_address[0]} {fmt % args}")

    # ═══ AUTH ═══
    def _check_auth(self):
        """Check PIN auth. Returns True if authorized."""
        if not AUTH_PIN:
            return True
        # Check cookie
        cookies = self.headers.get("Cookie", "")
        if f"auth={hashlib.sha256(AUTH_PIN.encode()).hexdigest()[:16]}" in cookies:
            return True
        return False

    def _auth_page(self):
        """Serve login page."""
        html = f'''<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Login - MixVault</title><style>body{{font-family:system-ui;display:flex;align-items:center;justify-content:center;min-height:100vh;background:#f5f5f4;margin:0}}
.box{{background:#fff;padding:40px;border-radius:16px;box-shadow:0 4px 12px rgba(0,0,0,.1);text-align:center;max-width:320px;width:90%}}
h1{{font-size:24px;margin-bottom:8px}}p{{color:#666;margin-bottom:20px}}
input{{width:100%;padding:12px;border:2px solid #e5e7eb;border-radius:12px;font-size:18px;text-align:center;outline:none;letter-spacing:4px}}
input:focus{{border-color:#2e7d32}}button{{width:100%;padding:12px;background:#2e7d32;color:#fff;border:none;border-radius:12px;font-size:16px;font-weight:600;cursor:pointer;margin-top:12px}}
.err{{color:#ef4444;font-size:13px;margin-top:8px;display:none}}</style></head>
<body><div class="box"><h1>🍳 MixVault</h1><p>Enter PIN to continue</p>
<form onsubmit="return login()"><input type="password" id="pin" maxlength="20" autofocus placeholder="••••">
<button type="submit">Enter</button><div class="err" id="err">Wrong PIN</div></form>
<script>function login(){{const p=document.getElementById('pin').value;
fetch('/api/auth',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{pin:p}})}})
.then(r=>r.json()).then(d=>{{if(d.ok)location.reload();else document.getElementById('err').style.display='block';}});return false;}}</script></div></body></html>'''
        body = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def _auth_login(self, req):
        """Handle PIN login."""
        pin = req.get("pin", "")
        if pin == AUTH_PIN:
            token = hashlib.sha256(AUTH_PIN.encode()).hexdigest()[:16]
            body = json.dumps({"ok": True}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", len(body))
            self.send_header("Set-Cookie", f"auth={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age=31536000")
            self.end_headers()
            self.wfile.write(body)
        else:
            self._json({"ok": False}, 401)

    # ═══ EXPORT ═══
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

    # ═══ RECIPE IMPORT ═══
    def _recipe_import(self, req):
        """Import a custom recipe."""
        required = ["name", "ingredients", "steps"]
        for f in required:
            if not req.get(f):
                return self._json({"error": f"missing field: {f}"}, 400)
        # Sanitize: strip HTML tags, enforce length limits
        def strip_html(s):
            return re.sub(r'<[^>]+>', '', str(s)) if s else ""
        def sanitize_str(s, max_len=500):
            return strip_html(s)[:max_len].strip()
        def sanitize_list(lst, max_items=100, max_len=500):
            if not isinstance(lst, list):
                lst = [lst]
            return [sanitize_str(x, max_len) for x in lst[:max_items] if x]

        name = sanitize_str(req["name"], 200)
        if not name:
            return self._json({"error": "name is empty after sanitization"}, 400)
        ingredients = sanitize_list(req["ingredients"])
        steps = sanitize_list(req["steps"], max_items=50, max_len=2000)
        if not ingredients or not steps:
            return self._json({"error": "ingredients and steps must be non-empty lists"}, 400)

        db = get_db()
        rid = hashlib.md5(name.encode()).hexdigest()[:12]
        if db.execute("SELECT 1 FROM recipes WHERE id=?", [rid]).fetchone():
            return self._json({"error": "recipe already exists", "id": rid}, 409)
        db.execute(
            "INSERT INTO recipes(id,name,country,lang,collection,image,total_time,yield,categories,ingredients,steps,nutrition,keywords) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (rid, name, sanitize_str(req.get("country","Custom"), 50), sanitize_str(req.get("lang","en"), 5),
             sanitize_str(req.get("collection","My Recipes"), 100), sanitize_str(req.get("image",""), 500),
             sanitize_str(req.get("totalTime",""), 20), sanitize_str(req.get("yield",""), 50),
             json.dumps(sanitize_list(req.get("categories",[]), 20, 100), ensure_ascii=False),
             json.dumps(ingredients, ensure_ascii=False),
             json.dumps(steps, ensure_ascii=False),
             json.dumps(req.get("nutrition",{}) if isinstance(req.get("nutrition"), dict) else {}, ensure_ascii=False),
             sanitize_str(req.get("keywords",""), 500))
        )
        db.execute(
            "INSERT INTO recipes_fts(id,name,ingredients,keywords,collection,categories) VALUES(?,?,?,?,?,?)",
            (rid, name, json.dumps(ingredients, ensure_ascii=False),
             sanitize_str(req.get("keywords",""), 500), sanitize_str(req.get("collection","My Recipes"), 100),
             json.dumps(sanitize_list(req.get("categories",[]), 20, 100), ensure_ascii=False))
        )
        db.commit()
        _meta_cache["ts"] = 0
        self._json({"ok": True, "id": rid})

    # ═══ POLLING (multi-device) ═══
    def _poll(self, params):
        """Return last-modified timestamps for multi-device sync."""
        db = get_db()
        shop_count = db.execute("SELECT count(*) FROM shopping_list").fetchone()[0]
        fav_count = db.execute("SELECT count(*) FROM favorites").fetchone()[0]
        self._json({"shopping_count": shop_count, "favorites_count": fav_count, "ts": int(time.time())})

    # ═══ HEALTH ═══
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


# ═══ OVERRIDE do_GET/do_POST for auth + new routes ═══
_orig_do_GET = Handler.do_GET
_orig_do_POST = Handler.do_POST

def _authed_do_GET(self):
    p = urlparse(self.path)
    if p.path == "/api/auth":
        return  # handled in POST
    if AUTH_PIN and not self._check_auth() and not p.path.startswith("/api/auth"):
        return self._auth_page()
    # New GET routes
    if p.path == "/api/export":
        return self._export(parse_qs(p.query))
    if p.path == "/api/poll":
        return self._poll(parse_qs(p.query))
    if p.path == "/api/health":
        return self._health(parse_qs(p.query))
    if p.path == "/api/cooking-state":
        return self._cooking_state_get(parse_qs(p.query))
    if p.path.startswith("/api/share/"):
        return self._share_recipe(unquote(p.path[11:]))
    if p.path == "/api/nutrition":
        return self._nutrition_search(parse_qs(p.query))
    return _orig_do_GET(self)

def _authed_do_POST(self):
    p = urlparse(self.path)
    if p.path == "/api/auth":
        content_len = int(self.headers.get("Content-Length", 0))
        if content_len > MAX_BODY_SIZE:
            return self.send_error(413)
        body = self.rfile.read(content_len)
        try: req = json.loads(body) if body else {}
        except: req = {}
        return self._auth_login(req)
    if AUTH_PIN and not self._check_auth():
        return self._json({"error": "unauthorized"}, 401)
    # New POST routes
    if p.path == "/api/recipe/import":
        content_len = int(self.headers.get("Content-Length", 0))
        if content_len > MAX_BODY_SIZE:
            return self.send_error(413)
        body = self.rfile.read(content_len)
        try: req = json.loads(body) if body else {}
        except: req = {}
        return self._recipe_import(req)
    if p.path.startswith("/api/recipe/delete/"):
        return self._recipe_delete(unquote(p.path[19:]))
    if p.path.startswith("/api/recipe/edit/"):
        content_len = int(self.headers.get("Content-Length", 0))
        if content_len > MAX_BODY_SIZE:
            return self.send_error(413)
        body = self.rfile.read(content_len)
        try: req = json.loads(body) if body else {}
        except: req = {}
        return self._recipe_edit(unquote(p.path[17:]), req)
    if p.path == "/api/cooking-state":
        content_len = int(self.headers.get("Content-Length", 0))
        if content_len > MAX_BODY_SIZE:
            return self.send_error(413)
        body = self.rfile.read(content_len)
        try: req = json.loads(body) if body else {}
        except: req = {}
        return self._cooking_state_save(req)
    if p.path == "/api/ai/create":
        content_len = int(self.headers.get("Content-Length", 0))
        if content_len > MAX_BODY_SIZE:
            return self.send_error(413)
        body = self.rfile.read(content_len)
        try: req = json.loads(body) if body else {}
        except: req = {}
        return self._ai_create(req)
    if p.path == "/api/ai/images":
        content_len = int(self.headers.get("Content-Length", 0))
        if content_len > MAX_BODY_SIZE:
            return self.send_error(413)
        body = self.rfile.read(content_len)
        try: req = json.loads(body) if body else {}
        except: req = {}
        return self._ai_image_search(req)
    if p.path == "/api/import/cookidoo":
        content_len = int(self.headers.get("Content-Length", 0))
        if content_len > MAX_BODY_SIZE:
            return self.send_error(413)
        body = self.rfile.read(content_len)
        try: req = json.loads(body) if body else {}
        except: req = {}
        return self._cookidoo_import(req)
    if p.path == "/api/substitutions":
        content_len = int(self.headers.get("Content-Length", 0))
        if content_len > MAX_BODY_SIZE:
            return self.send_error(413)
        body = self.rfile.read(content_len)
        try: req = json.loads(body) if body else {}
        except: req = {}
        return self._substitutions(req)
    return _orig_do_POST(self)

Handler.do_GET = _authed_do_GET
Handler.do_POST = _authed_do_POST


# ═══ MAINTENANCE THREAD ═══
def _maintenance_loop():
    """Periodic WAL checkpoint, vacuum, and backup."""
    while True:
        time.sleep(3600)  # Every hour
        try:
            db = get_db()
            # WAL checkpoint
            db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            log.info("WAL checkpoint done")
            # Backup (keep last 3)
            ts = time.strftime("%Y%m%d_%H%M%S")
            backup_path = BACKUP_DIR / f"recipes_{ts}.db"
            src_db = sqlite3.connect(DB_PATH)
            dst_db = sqlite3.connect(str(backup_path))
            src_db.backup(dst_db)
            dst_db.close()
            src_db.close()
            log.info(f"Backup created: {backup_path.name}")
            # Prune old backups (keep 3)
            backups = sorted(BACKUP_DIR.glob("recipes_*.db"))
            for old in backups[:-3]:
                old.unlink()
                log.info(f"Pruned old backup: {old.name}")
        except Exception as e:
            log.error(f"Maintenance error: {e}")

def _daily_vacuum():
    """Run VACUUM once a day."""
    while True:
        time.sleep(86400)  # 24h
        try:
            db = get_db()
            db.execute("PRAGMA optimize")
            log.info("DB optimize done")
        except Exception as e:
            log.error(f"Vacuum error: {e}")


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


# ═══ GRACEFUL SHUTDOWN ═══
srv = None

def _shutdown(signum, frame):
    log.info(f"Received signal {signum}, shutting down...")
    if srv:
        threading.Thread(target=srv.shutdown).start()

signal.signal(signal.SIGTERM, _shutdown)
signal.signal(signal.SIGINT, _shutdown)


if __name__ == "__main__":
    get_db()
    # Verify DB has recipes table
    tables = [r[0] for r in get_db().execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    if "recipes" not in tables:
        log.error(f"ERROR: Database at {DB_PATH} has no 'recipes' table.")
        log.error(f"  Make sure recipes.db is mounted correctly.")
        log.error(f"  Expected path: {DB_PATH}")
        log.error(f"  Existing tables: {tables or '(empty database)'}")
        sys.exit(1)
    total = get_db().execute("SELECT count(*) FROM recipes").fetchone()[0]
    log.info(f"🍳 MixVault — {total:,} recipes")
    log.info(f"   http://localhost:{PORT}")

    # Start maintenance threads
    threading.Thread(target=_maintenance_loop, daemon=True).start()
    threading.Thread(target=_daily_vacuum, daemon=True).start()

    srv = ThreadingHTTPServer(("", PORT), Handler)
    srv.allow_reuse_address = True
    try:
        srv.serve_forever()
    finally:
        log.info("Server stopped.")
        # Final WAL checkpoint
        try:
            get_db().execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except:
            pass
