"""
Access-key sessions.

Signing in means presenting one long random key (see lib/users.py) — no
usernames, no passwords, no directory. Responses are deliberately uniform: a
wrong key and an unknown key are indistinguishable, and nothing here reveals
how many identities exist.
"""
import base64
import hashlib
import hmac
import json
import re
import time

from ..config import ALLOW_SIGNUP, AUTH_PIN, COOKIE, SESSION_MAX_AGE, TRUST_PROXY, log
from ..users import create_user, hash_key, lookup_by_hash, looks_like_key, users_exist

# Per-IP throttle so a stolen URL can't be used to grind through the key space.
_FAIL_WINDOW = 300
_FAIL_LIMIT = 8
_LOCKOUT = 60
_MAX_TRACKED_IPS = 4096
_failures: dict[str, list[float]] = {}


def _client_ip(self) -> str:
    """
    Throttle key. X-Forwarded-For is only honoured behind a proxy you control
    (TRUST_PROXY=1); otherwise a caller could rotate it to dodge the limit.
    """
    if TRUST_PROXY:
        fwd = self.headers.get("X-Forwarded-For", "")
        if fwd:
            return fwd.split(",")[0].strip() or "?"
    return self.client_address[0] or "?"


def _throttled(self) -> bool:
    ip = _client_ip(self)
    now = time.time()
    hits = [t for t in _failures.get(ip, []) if now - t < _FAIL_WINDOW]
    _failures[ip] = hits
    return len(hits) >= _FAIL_LIMIT and now - hits[-1] < _LOCKOUT


def _record_failure(self):
    now = time.time()
    if len(_failures) >= _MAX_TRACKED_IPS:
        # Drop entries whose window has passed so the map cannot grow without bound.
        for ip in [k for k, v in _failures.items() if not v or now - v[-1] > _FAIL_WINDOW]:
            del _failures[ip]
        if len(_failures) >= _MAX_TRACKED_IPS:
            _failures.clear()
    _failures.setdefault(_client_ip(self), []).append(now)


def _pin_token() -> str:
    """The legacy PIN cookie's value. Compared with `hmac.compare_digest`."""
    return hashlib.sha256(AUTH_PIN.encode()).hexdigest()[:16]


def _cookies(self) -> dict[str, str]:
    jar = {}
    for part in (self.headers.get("Cookie", "") or "").split(";"):
        name, _, value = part.strip().partition("=")
        if name:
            jar[name] = value
    return jar


def _secure_flag(self) -> str:
    """
    `Secure` when the browser reached us over TLS — which only a proxy can tell
    us, and only a proxy we trust. Believing an arbitrary X-Forwarded-Proto would
    let a caller mark the cookie Secure over plain HTTP, where the browser then
    refuses to store it at all.
    """
    if not TRUST_PROXY:
        return ""
    proto = self.headers.get("X-Forwarded-Proto", "")
    return "; Secure" if proto.split(",")[0].strip() == "https" else ""


def _set_cookie(self, key_hash: str) -> str:
    return f"{COOKIE}={key_hash}; Path=/; HttpOnly; SameSite=Lax; Max-Age={SESSION_MAX_AGE}{_secure_flag(self)}"


def _check_auth(self):
    """
    Resolve the caller and stash it on `self.user_id`. True means "may proceed".

    Three modes:
      * keys exist            → a valid access-key cookie is required
      * no keys, AUTH_PIN set → legacy shared-PIN gate, everything owned by ''
      * no keys, no PIN       → open single-user install (unchanged behaviour)
    """
    self.user_id = ""
    if users_exist():
        uid = lookup_by_hash(_cookies(self).get(COOKIE, ""))
        if uid:
            self.user_id = uid
            return True
        return False
    if not AUTH_PIN:
        return True
    return hmac.compare_digest(_cookies(self).get("auth", ""), _pin_token())


_PAGE = """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MixVault</title><link rel="icon" type="image/svg+xml" href="/favicon.svg">
<style>
:root{color-scheme:light dark}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Inter',system-ui,-apple-system,sans-serif;display:flex;align-items:center;
justify-content:center;min-height:100dvh;background:#f5f5f4;color:#1a1a1a;padding:20px}
@media(prefers-color-scheme:dark){body{background:#121212;color:#e0e0e0}
.box{background:#1e1e1e!important;box-shadow:0 4px 12px rgba(0,0,0,.4)!important}
input{background:#121212!important;color:#e0e0e0!important;border-color:#333!important}
.alt{color:#999!important}}
.box{background:#fff;padding:32px 28px;border-radius:18px;box-shadow:0 1px 2px rgba(0,0,0,.04),
0 8px 24px rgba(0,0,0,.08);max-width:430px;width:100%}
.logo{display:flex;align-items:center;gap:8px;font-size:20px;font-weight:700;color:#1b5e20;margin-bottom:6px}
.logo svg{width:26px;height:26px}
p.sub{color:#6b7280;font-size:14px;line-height:1.5;margin-bottom:20px}
label{display:block;font-size:12px;font-weight:600;color:#6b7280;margin-bottom:6px}
.field{position:relative}
input{width:100%;padding:13px 52px 13px 14px;border:2px solid #e5e7eb;border-radius:12px;font-size:15px;
font-family:ui-monospace,SFMono-Regular,Menlo,monospace;outline:none;background:#f5f5f4}
.reveal{position:absolute;right:6px;top:50%;transform:translateY(-50%);width:auto;margin:0;padding:6px 10px;
background:none;color:#6b7280;font-size:12px;font-weight:600;border-radius:8px}
.reveal:hover{background:#f0f0ef;color:#1a1a1a}
@media(prefers-color-scheme:dark){.reveal:hover{background:#2a2a2a!important;color:#e0e0e0!important}}
input:focus{border-color:#2e7d32;background:#fff}
button{width:100%;padding:13px;background:#2e7d32;color:#fff;border:none;border-radius:12px;
font-size:15px;font-weight:600;cursor:pointer;margin-top:12px;font-family:inherit}
button:hover{background:#1b5e20}
button.ghost{background:none;color:#2e7d32;border:1.5px solid #e5e7eb;margin-top:8px}
.err{color:#ef4444;font-size:13px;margin-top:10px;min-height:18px}
.alt{font-size:12px;color:#9ca3af;margin-top:16px;line-height:1.5;text-align:center}
.keybox{margin-top:16px;padding:14px;border:1.5px dashed #2e7d32;border-radius:12px;
font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:15px;word-break:break-all;text-align:center}
.warn{font-size:12px;color:#e65100;margin-top:8px;line-height:1.5}
@media(max-width:430px){input{font-size:13px;padding-right:48px}.reveal{font-size:11px;padding:5px 8px}}
</style></head><body><div class="box">
<div class="logo"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
<circle cx="12" cy="12" r="10"/><path d="M8 12l2 2 4-4"/></svg>MixVault</div>
<p class="sub">__SUB__</p>
<form id="f" autocomplete="off">
<label for="key">__LABEL__</label>
<div class="field">
<input id="key" name="key" type="password" autocomplete="off" autofocus
 placeholder="__PLACEHOLDER__" spellcheck="false" enterkeyhint="go">
<button class="reveal" type="button" id="reveal" aria-label="Show key">Show</button>
</div>
<button type="submit">Continue</button>
</form>
<div class="err" id="err"></div>
__SIGNUP__
__HINT__
<div id="out"></div>
</div>
<script>
/* Every handler is attached here rather than with an onclick attribute: the page
   is served under a CSP that allows this one script by hash, and inline attributes
   would need 'unsafe-hashes' to run. */
const err=document.getElementById('err'),out=document.getElementById('out');
const keyInput=document.getElementById('key'),revealBtn=document.getElementById('reveal');
revealBtn.addEventListener('click',()=>{
  const shown=keyInput.type==='text';
  keyInput.type=shown?'password':'text';
  revealBtn.textContent=shown?'Show':'Hide';
  revealBtn.setAttribute('aria-label',shown?'Show key':'Hide key');
  keyInput.focus();
});
document.getElementById('f').addEventListener('submit',async e=>{
  e.preventDefault();err.textContent='';
  const key=document.getElementById('key').value;
  const r=await fetch('/api/auth',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({key})});
  const d=await r.json().catch(()=>({}));
  if(d.ok)location.replace('/');
  else err.textContent=d.error||'That key was not recognised.';
});
const signupBtn=document.getElementById('signupBtn');
if(signupBtn) signupBtn.addEventListener('click',async()=>{
  err.textContent='';
  const label=prompt('Name this vault (optional, only you see it):')||'';
  const r=await fetch('/api/auth/new',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({label})});
  const d=await r.json().catch(()=>({}));
  if(!d.ok){err.textContent=d.error||'Could not create a vault.';return;}
  document.getElementById('f').style.display='none';
  const box=document.createElement('div');box.className='keybox';box.textContent=d.key;
  const warn=document.createElement('p');warn.className='warn';
  warn.textContent='Save this key now — it is shown once and cannot be recovered. '+
    'Anyone with it can open your vault.';
  const go=document.createElement('button');go.textContent='I saved it — continue';
  go.addEventListener('click',()=>location.replace('/'));
  out.replaceChildren(box,warn,go);
});
</script></body></html>"""


def _page_csp() -> str:
    """
    CSP for the login page, allowing its own inline script by hash.

    The hash is taken from the template itself, so editing the script above cannot
    silently break the page — there is no second copy to keep in step.
    """
    digests = [
        "'sha256-" + base64.b64encode(hashlib.sha256(body.encode()).digest()).decode() + "'"
        for body in re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", _PAGE, re.S)
    ]
    return "; ".join([
        "default-src 'none'",
        "script-src " + " ".join(digests),
        "style-src 'unsafe-inline'",
        "img-src 'self' data:",
        "connect-src 'self'",
        "form-action 'none'",
        "base-uri 'none'",
        "frame-ancestors 'none'",
    ])


_PAGE_CSP = _page_csp()


def _auth_page(self):
    """The only unauthenticated HTML surface: ask for an access key."""
    if users_exist():
        sub = "Enter your access key to open your recipes. Each key is a separate, private vault."
        label = "Access key"
        placeholder = "mv_xxxx-xxxx-xxxx-xxxx-xxxx-xxxx"
    else:
        sub = "Enter the PIN to continue."
        label = "PIN"
        placeholder = "••••"
    can_signup = ALLOW_SIGNUP and users_exist()
    signup = (
        '<button class="ghost" type="button" id="signupBtn">Create a new vault</button>'
        if can_signup
        else ""
    )
    if not users_exist():
        hint = ""
    elif can_signup:
        hint = '<p class="alt">A new vault starts empty — the recipe library is shared, your cooking is not.</p>'
    else:
        hint = '<p class="alt">Lost your key, or need one? Ask whoever runs this MixVault.</p>'
    html = (
        _PAGE.replace("__SUB__", sub)
        .replace("__LABEL__", label)
        .replace("__PLACEHOLDER__", placeholder)
        .replace("__SIGNUP__", signup)
        .replace("__HINT__", hint)
    )
    body = html.encode()
    self.send_response(200)
    self.send_header("Content-Type", "text/html; charset=utf-8")
    self.send_header("Content-Length", len(body))
    self.send_header("Cache-Control", "no-store")
    self.send_header("Content-Security-Policy", _PAGE_CSP)
    self.end_headers()
    self.wfile.write(body)


def _send_json(self, data, status=200, cookie=None):
    body = json.dumps(data).encode()
    self.send_response(status)
    self.send_header("Content-Type", "application/json")
    self.send_header("Content-Length", len(body))
    self.send_header("Cache-Control", "no-store")
    for value in ([cookie] if isinstance(cookie, str) else cookie or []):
        self.send_header("Set-Cookie", value)
    self.end_headers()
    self.wfile.write(body)


def _auth_login(self, req):
    """Exchange an access key (or legacy PIN) for a session cookie."""
    if _throttled(self):
        return _send_json(self, {"ok": False, "error": "Too many attempts. Wait a minute."}, 429)

    secret = str(req.get("key") or req.get("pin") or "")

    if users_exist():
        if looks_like_key(secret):
            kh = hash_key(secret)
            if lookup_by_hash(kh):
                return _send_json(self, {"ok": True}, cookie=_set_cookie(self, kh))
        _record_failure(self)
        log.info(f"failed access-key attempt from {_client_ip(self)}")
        # Same response for malformed, unknown and revoked keys.
        return _send_json(self, {"ok": False, "error": "That key was not recognised."}, 401)

    if AUTH_PIN and hmac.compare_digest(secret, AUTH_PIN):
        cookie = (f"auth={_pin_token()}; Path=/; HttpOnly; SameSite=Lax;"
                  f" Max-Age={SESSION_MAX_AGE}{_secure_flag(self)}")
        return _send_json(self, {"ok": True}, cookie=cookie)

    _record_failure(self)
    return _send_json(self, {"ok": False, "error": "That key was not recognised."}, 401)


def _auth_signup(self, req):
    """
    Mint a vault key.

    Two callers: someone already signed in creating a key for another person
    (always allowed — they can already see their own vault, and a new vault tells
    them nothing about existing ones), or a stranger on the login page, which
    requires ALLOW_SIGNUP. Only the second case takes over the session.
    """
    invited_by_member = bool(getattr(self, "user_id", ""))
    if not invited_by_member and not (ALLOW_SIGNUP and users_exist()):
        return _send_json(self, {"ok": False, "error": "Vault creation is disabled."}, 403)
    if _throttled(self):
        return _send_json(self, {"ok": False, "error": "Too many attempts. Wait a minute."}, 429)
    uid, key = create_user(str(req.get("label") or ""))
    log.info(f"new vault {uid} created ({'invite' if invited_by_member else 'self-serve'})")
    cookie = None if invited_by_member else _set_cookie(self, hash_key(key))
    return _send_json(self, {"ok": True, "key": key, "id": uid}, cookie=cookie)


def _auth_logout(self, req=None):
    """Clear both the access-key cookie and the legacy PIN cookie."""
    secure = _secure_flag(self)
    expired = [f"{name}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0{secure}"
               for name in (COOKIE, "auth")]
    return _send_json(self, {"ok": True}, cookie=expired)


def _session(self, params=None):
    """
    What the signed-in client may know about itself — and nothing about anyone else.
    """
    self._json({
        "multi_user": users_exist(),
        "signed_in": bool(self.user_id),
        "label": get_label(self.user_id) if self.user_id else "",
        "signup_enabled": bool(ALLOW_SIGNUP),
    })


def get_label(uid: str) -> str:
    from ..db import get_db

    row = get_db().execute("SELECT label FROM vault.users WHERE id=?", [uid]).fetchone()
    return row["label"] if row else ""
