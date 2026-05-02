"""Authentication handlers: PIN check, login page, login action."""
import json, hashlib
from ..config import AUTH_PIN


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
