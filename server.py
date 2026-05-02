#!/usr/bin/env python3
"""MixVault - SQLite-backed server with FTS5 search."""
import json, sqlite3, threading, time, signal, sys
from http.server import HTTPServer, SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn
from urllib.parse import urlparse, parse_qs, unquote

from lib.config import *
from lib.db import get_db
from lib.handlers.recipes import (
    _search, _recipe, _meta, _similar, _favorites_list, _translate,
    _recipe_import, _recipe_edit, _recipe_delete, _cookidoo_import, _nutrition_search,
)
from lib.handlers.shopping import (
    _shopping_list, _shopping_add, _shopping_toggle, _shopping_clear,
    _shopping_restore, _shopping_delete,
)
from lib.handlers.cooking import (
    _history_list, _mark_cooked, _cooking_state_get, _cooking_state_save,
)
from lib.handlers.ai_handlers import _ai, _ai_create, _ai_image_search, _substitutions
from lib.handlers.auth import _check_auth, _auth_page, _auth_login
from lib.handlers.misc import _export, _poll, _health, _share_recipe, _note_get, _note_save, _restore, _tags_get, _tags_save


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

    def log_message(self, fmt, *args):
        log.info(f"{self.client_address[0]} {fmt % args}")


# Assign handler functions to the Handler class
Handler._search = _search
Handler._recipe = _recipe
Handler._meta = _meta
Handler._similar = _similar
Handler._favorites_list = _favorites_list
Handler._translate = _translate
Handler._recipe_import = _recipe_import
Handler._recipe_edit = _recipe_edit
Handler._recipe_delete = _recipe_delete
Handler._cookidoo_import = _cookidoo_import
Handler._nutrition_search = _nutrition_search
Handler._shopping_list = _shopping_list
Handler._shopping_add = _shopping_add
Handler._shopping_toggle = _shopping_toggle
Handler._shopping_clear = _shopping_clear
Handler._shopping_restore = _shopping_restore
Handler._shopping_delete = _shopping_delete
Handler._history_list = _history_list
Handler._mark_cooked = _mark_cooked
Handler._cooking_state_get = _cooking_state_get
Handler._cooking_state_save = _cooking_state_save
Handler._ai = _ai
Handler._ai_create = _ai_create
Handler._ai_image_search = _ai_image_search
Handler._substitutions = _substitutions
Handler._check_auth = _check_auth
Handler._auth_page = _auth_page
Handler._auth_login = _auth_login
Handler._export = _export
Handler._poll = _poll
Handler._health = _health
Handler._share_recipe = _share_recipe
Handler._note_get = _note_get
Handler._note_save = _note_save
Handler._restore = _restore
Handler._tags_get = _tags_get
Handler._tags_save = _tags_save


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
    if p.path.startswith("/api/tags/"):
        return self._tags_get(unquote(p.path[10:]))
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
    if p.path.startswith("/api/tags/"):
        content_len = int(self.headers.get("Content-Length", 0))
        if content_len > MAX_BODY_SIZE:
            return self.send_error(413)
        body = self.rfile.read(content_len)
        try: req = json.loads(body) if body else {}
        except: req = {}
        return self._tags_save(unquote(p.path[10:]), req)
    if p.path == "/api/import/restore":
        content_len = int(self.headers.get("Content-Length", 0))
        if content_len > MAX_BODY_SIZE:
            return self.send_error(413)
        body = self.rfile.read(content_len)
        try: req = json.loads(body) if body else {}
        except: req = {}
        return self._restore(req)
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
