"""
Access-key identities.

There are no usernames and no passwords. Each person holds one long random
*access key* (128 bits, printed once when the key is created):

    mv_7q4k-x9f2-h8ta-3wnp-6dbe-5rjm

The key is the whole credential: typing it in signs you in, and everything the
app stores (favourites, cooking history, shopping list, notes, tags) is scoped
to the identity derived from it. Only `sha256(key)` is stored, so the database
never contains a usable key, and nothing in the HTTP API can list identities or
count them — a signed-in person cannot tell whether anybody else exists.
"""
import hashlib
import re
import secrets

from .db import get_db

# Crockford base32 minus look-alikes (I, L, O, U) so keys survive being read aloud.
_ALPHABET = "0123456789abcdefghjkmnpqrstvwxyz"
_PREFIX = "mv_"
_GROUPS = 6
_GROUP_LEN = 4


def generate_key() -> str:
    """A fresh access key with ~120 bits of entropy, grouped for readability."""
    chars = "".join(secrets.choice(_ALPHABET) for _ in range(_GROUPS * _GROUP_LEN))
    groups = [chars[i : i + _GROUP_LEN] for i in range(0, len(chars), _GROUP_LEN)]
    return _PREFIX + "-".join(groups)


def normalize_key(raw: str) -> str:
    """
    Canonical form used for hashing: lowercase, no separators, no prefix.

    Lets people type `MV_7Q4K X9F2…`, `7q4k-x9f2…` or paste the exact string.
    """
    s = str(raw or "").strip().lower()
    if s.startswith(_PREFIX):
        s = s[len(_PREFIX) :]
    return re.sub(r"[^0-9a-z]", "", s)


def hash_key(raw: str) -> str:
    """Stable lookup token for a key. Also what the session cookie carries."""
    return hashlib.sha256(("mixvault:" + normalize_key(raw)).encode()).hexdigest()


def looks_like_key(raw: str) -> bool:
    return len(normalize_key(raw)) == _GROUPS * _GROUP_LEN


def user_id_for(key_hash: str) -> str:
    return key_hash[:16]


#: Vault tables keyed by user_id.
ORPHAN_TABLES = (
    "favorites", "recent", "shopping_list", "cooking_history",
    "recipe_notes", "cooking_state", "recipe_tags",
)


def create_user(label: str = "", claim_orphans: bool = False) -> tuple[str, str]:
    """
    Register a new identity. Returns `(user_id, access_key)`.

    The key is returned once and never recoverable afterwards. With
    `claim_orphans`, rows that predate multi-user mode (`user_id = ''`) are
    handed to this identity — used for the first key on an existing install.
    """
    db = get_db()
    key = generate_key()
    kh = hash_key(key)
    uid = user_id_for(kh)
    db.execute(
        "INSERT INTO vault.users(id, key_hash, label) VALUES(?,?,?)",
        [uid, kh, (label or "").strip()[:60]],
    )
    if claim_orphans:
        for table in ORPHAN_TABLES:
            db.execute(f"UPDATE vault.{table} SET user_id=? WHERE user_id=''", [uid])
    db.commit()
    return uid, key


def lookup_by_hash(key_hash: str) -> str | None:
    """Resolve a session cookie / key hash to a user id."""
    if not key_hash or len(key_hash) != 64 or not re.fullmatch(r"[0-9a-f]{64}", key_hash):
        return None
    row = get_db().execute("SELECT id FROM vault.users WHERE key_hash=?", [key_hash]).fetchone()
    return row["id"] if row else None


def users_exist() -> bool:
    """True once at least one key has been created — i.e. multi-user mode is on."""
    return get_db().execute("SELECT 1 FROM vault.users LIMIT 1").fetchone() is not None


def list_users() -> list[dict]:
    """Admin/CLI only. Deliberately never exposed over HTTP."""
    rows = get_db().execute(
        "SELECT id, label, created_at FROM vault.users ORDER BY created_at"
    ).fetchall()
    return [dict(r) for r in rows]


def revoke_user(uid: str, delete_data: bool = False) -> bool:
    """Invalidate a key. Optionally wipe everything that identity stored."""
    db = get_db()
    if not db.execute("SELECT 1 FROM vault.users WHERE id=?", [uid]).fetchone():
        return False
    db.execute("DELETE FROM vault.users WHERE id=?", [uid])
    if delete_data:
        for table in ORPHAN_TABLES:
            db.execute(f"DELETE FROM vault.{table} WHERE user_id=?", [uid])
        db.execute("DELETE FROM vault.user_recipes WHERE owner=?", [uid])
    db.commit()
    return True
