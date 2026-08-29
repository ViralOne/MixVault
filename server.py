#!/usr/bin/env python3
"""MixVault - SQLite-backed server with FTS5 search."""
import base64, hashlib, json, re, sqlite3, threading, time, signal, sys
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from socketserver import ThreadingMixIn
from urllib.parse import urlparse, parse_qs, unquote

from lib.config import *
from lib.config import CORS_ORIGINS
from lib.db import get_db, find_recipe, init_db
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
from lib.handlers.auth import (
    _check_auth, _auth_page, _auth_login, _auth_signup, _auth_logout, _session,
)
from lib.handlers.misc import _export, _poll, _health, _share_recipe, _note_get, _note_save, _restore, _tags_get, _tags_save, _tags_list


BASE_HEADERS = (
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
    ("Referrer-Policy", "no-referrer"),
    ("Permissions-Policy", "geolocation=(), microphone=(), camera=(), payment=()"),
)

_app_csp = None


def app_csp():
    """
    CSP for the app shell.

    The inline theme script in index.html is allowed by hash, read from the file
    Vite actually produced — so a rebuild that changes that script does not need a
    matching edit here. Google Fonts is the one third party the page talks to.
    """
    global _app_csp
    if _app_csp is None:
        digests = []
        try:
            shell = (Path(STATIC) / "index.html").read_text(encoding="utf-8")
            for body in re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", shell, re.S):
                digests.append("'sha256-" +
                               base64.b64encode(hashlib.sha256(body.encode()).digest()).decode() + "'")
        except OSError:
            log.warning("could not read index.html for CSP hashes")
        _app_csp = "; ".join([
            "default-src 'self'",
            "script-src 'self' " + " ".join(digests),
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
            "font-src 'self' https://fonts.gstatic.com",
            # Recipe photos are hotlinked from the sources the library was built from.
            "img-src 'self' data: https:",
            "connect-src 'self'",
            "frame-ancestors 'none'",
            "base-uri 'none'",
            "form-action 'self'",
        ])
    return _app_csp


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
        req = _read_json(self)
        if req is None:
            return
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

    def send_head(self):
        """
        Static files, with cache rules that suit an app behind a login:

        index.html must always be revalidated — a cached copy would let a
        signed-out browser paint the app shell and then fire a burst of 401s.
        Asset filenames carry a content hash, so those are safe to keep forever.
        """
        path = urlparse(self.path).path
        if path.startswith("/assets/"):
            self._extra_headers = [("Cache-Control", "public, max-age=31536000, immutable")]
        else:
            self._extra_headers = [("Cache-Control", "no-cache")]
        if path in ("/", "/index.html"):
            self._extra_headers.append(("Content-Security-Policy", app_csp()))
        return super().send_head()

    def end_headers(self):
        for name, value in getattr(self, "_extra_headers", ()):
            self.send_header(name, value)
        for name, value in BASE_HEADERS:
            self.send_header(name, value)
        self._extra_headers = ()
        super().end_headers()

    def _cors_headers(self):
        """
        Only origins named in CORS_ORIGINS may talk to the API with credentials.
        Echoing back whatever Origin arrived would let any site read a signed-in
        vault the moment the cookie policy loosened.
        """
        origin = self.headers.get("Origin", "")
        if origin and origin in CORS_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Credentials", "true")

    def _json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",len(body))
        # Responses are per-vault: keep them out of shared and back-button caches.
        self.send_header("Cache-Control", "no-store, private")
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        """Handle CORS preflight."""
        self.send_response(204)
        self._cors_headers()
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _favorite_toggle(self, rid):
        db = get_db()
        uid = self.user_id
        if not find_recipe(db, rid, uid):
            return self._json({"error": "not found"}, 404)
        exists = db.execute("SELECT 1 FROM vault.favorites WHERE user_id=? AND recipe_id=?",
                            [uid, rid]).fetchone()
        if exists:
            db.execute("DELETE FROM vault.favorites WHERE user_id=? AND recipe_id=?", [uid, rid])
            db.commit()
            self._json({"favorited":False})
        else:
            db.execute("INSERT OR IGNORE INTO vault.favorites(user_id,recipe_id) VALUES(?,?)", [uid, rid])
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
Handler._auth_signup = _auth_signup
Handler._auth_logout = _auth_logout
Handler._session = _session
Handler._export = _export
Handler._poll = _poll
Handler._health = _health
Handler._share_recipe = _share_recipe
Handler._note_get = _note_get
Handler._note_save = _note_save
Handler._restore = _restore
Handler._tags_get = _tags_get
Handler._tags_list = _tags_list
Handler._tags_save = _tags_save


# ═══ OVERRIDE do_GET/do_HEAD/do_POST for auth + new routes ═══
_orig_do_GET = Handler.do_GET
_orig_do_HEAD = Handler.do_HEAD
_orig_do_POST = Handler.do_POST

def _authed_do_GET(self):
    p = urlparse(self.path)
    # Reset per request: a keep-alive connection reuses this handler instance.
    self.user_id, self.authed = "", False
    if p.path.startswith("/api/auth"):
        return self.send_error(405)  # auth is POST-only
    # _check_auth resolves the caller and sets self.user_id.
    self.authed = self._check_auth()
    if not self.authed:
        # Liveness probes (docker healthcheck) must work without a key.
        if p.path == "/api/health":
            return self._health(parse_qs(p.query))
        if p.path.startswith("/api/"):
            return self._json({"error": "unauthorized"}, 401)
        if p.path == "/favicon.svg":
            return _orig_do_GET(self)
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
    if p.path == "/api/session":
        return self._session(parse_qs(p.query))
    if p.path == "/api/tags":
        return self._tags_list(parse_qs(p.query))
    if p.path.startswith("/api/tags/"):
        return self._tags_get(unquote(p.path[10:]))
    return _orig_do_GET(self)

def _read_json(self):
    """
    The request body as a dict, or None when it was refused (413/400 already sent).

    Every POST route goes through this: reading Content-Length by hand in each
    handler is how one of them ends up without a size check.
    """
    try:
        content_len = int(self.headers.get("Content-Length", 0) or 0)
    except ValueError:
        self.send_error(400, "Bad Content-Length")
        return None
    if content_len < 0 or content_len > MAX_BODY_SIZE:
        self.send_error(413, "Request body too large")
        return None
    body = self.rfile.read(content_len)
    try:
        parsed = json.loads(body) if body else {}
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _origin_ok(self) -> bool:
    """
    Refuse writes that another site set in motion.

    `SameSite=Lax` already keeps the session cookie off cross-site POSTs, but
    /api/auth needs no cookie to work: without this check a page could quietly
    sign a visitor into *its* vault and then read whatever they cooked next.
    Requests with no Origin at all (curl, scripts) carry no ambient credentials
    from a browser, so they pass.

    `Sec-Fetch-Site` decides when the browser sent it: it is set by the browser,
    cannot be forged from a page, and stays correct behind a proxy that rewrites
    Host. Comparing Origin to Host is only the fallback for browsers too old to
    send it.
    """
    origin = self.headers.get("Origin", "")
    if origin and origin in CORS_ORIGINS:
        return True
    site = self.headers.get("Sec-Fetch-Site", "")
    if site:
        return site in ("same-origin", "none")
    if origin:
        return origin.split("//", 1)[-1] == self.headers.get("Host", "")
    return True


def _authed_do_HEAD(self):
    """HEAD would otherwise skip the gate and confirm which files exist."""
    self.user_id, self.authed = "", False
    self.authed = self._check_auth()
    if not self.authed:
        self.send_response(401)
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        return
    return _orig_do_HEAD(self)


#: POST routes taking a JSON body: exact path → handler.
_POST_ROUTES = {
    "/api/recipe/import":  lambda s, req: s._recipe_import(req),
    "/api/cooking-state":  lambda s, req: s._cooking_state_save(req),
    "/api/ai/create":      lambda s, req: s._ai_create(req),
    "/api/ai/images":      lambda s, req: s._ai_image_search(req),
    "/api/import/cookidoo": lambda s, req: s._cookidoo_import(req),
    "/api/import/restore": lambda s, req: s._restore(req),
    "/api/substitutions":  lambda s, req: s._substitutions(req),
}

#: Same, for routes carrying an id in the path: prefix → handler(id, body).
_POST_PREFIXES = (
    ("/api/recipe/edit/", lambda s, rid, req: s._recipe_edit(rid, req)),
    ("/api/tags/",        lambda s, rid, req: s._tags_save(rid, req)),
)


def _authed_do_POST(self):
    p = urlparse(self.path)
    self.user_id, self.authed = "", False
    if not _origin_ok(self):
        return self._json({"error": "cross-site request refused"}, 403)
    if p.path in ("/api/auth", "/api/auth/new", "/api/auth/logout"):
        req = _read_json(self)
        if req is None:
            return
        self.authed = self._check_auth()  # sets self.user_id for signup/logout
        if p.path == "/api/auth":
            return self._auth_login(req)
        if p.path == "/api/auth/new":
            return self._auth_signup(req)
        return self._auth_logout(req)
    self.authed = self._check_auth()
    if not self.authed:
        return self._json({"error": "unauthorized"}, 401)

    if p.path.startswith("/api/recipe/delete/"):
        return self._recipe_delete(unquote(p.path[19:]))
    if p.path in _POST_ROUTES:
        req = _read_json(self)
        return None if req is None else _POST_ROUTES[p.path](self, req)
    for prefix, handler in _POST_PREFIXES:
        if p.path.startswith(prefix):
            req = _read_json(self)
            return None if req is None else handler(self, unquote(p.path[len(prefix):]), req)
    return _orig_do_POST(self)

Handler.do_GET = _authed_do_GET
Handler.do_HEAD = _authed_do_HEAD
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
            db.execute("PRAGMA vault.wal_checkpoint(TRUNCATE)")
            # Backup both databases (keep last 3 of each)
            ts = time.strftime("%Y%m%d_%H%M%S")
            for prefix, path in (("recipes", DB_PATH), ("vault", VAULT_DB_PATH)):
                backup_path = BACKUP_DIR / f"{prefix}_{ts}.db"
                src_db = sqlite3.connect(path)
                dst_db = sqlite3.connect(str(backup_path))
                src_db.backup(dst_db)
                dst_db.close()
                src_db.close()
                if prefix == "vault":
                    # A copy of the vault is as sensitive as the vault itself.
                    backup_path.chmod(0o600)
                log.info(f"Backup created: {backup_path.name}")
                # Only rotate our own timestamped files: a snapshot someone parked
                # here by hand (recipes_pre_vault_….db) is not ours to delete.
                for old in sorted(BACKUP_DIR.glob(f"{prefix}_[0-9]*.db"))[:-3]:
                    old.unlink()
                    log.info(f"Pruned old backup: {old.name}")
        except Exception as e:
            log.error(f"Maintenance error: {e}")

def _daily_vacuum():
    """Let SQLite re-plan its indexes once a day."""
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
    init_db()   # create/upgrade the vault before any request can attach it
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
    from lib.users import users_exist
    log.info(f"🍳 MixVault — {total:,} recipes")
    log.info(f"   library: {DB_PATH}")
    log.info(f"   vault:   {VAULT_DB_PATH}")
    if users_exist():
        log.info("   access keys active — every request needs one")
    elif AUTH_PIN:
        log.info("   single vault, PIN protected")
    else:
        log.info("   single vault, open (create keys: python3 scripts/users.py add)")
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
        # Final WAL checkpoint on both databases
        try:
            get_db().execute("PRAGMA wal_checkpoint(TRUNCATE)")
            get_db().execute("PRAGMA vault.wal_checkpoint(TRUNCATE)")
        except:
            pass
