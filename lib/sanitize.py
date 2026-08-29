"""
Shaping untrusted input before it reaches the database.

Every write path shares these helpers so a recipe that arrives through the AI
creator, a Cookidoo import, an edit form or a restored backup ends up under the
same limits. Anything stored unbounded is a way to fill someone's disk; anything
stored with markup in it is a way to smuggle HTML into the share page.
"""
import json
import re

#: Ceilings for the free-text fields a person can create many of.
MAX_NOTE = 5_000
MAX_TAG = 40
MAX_TAGS_PER_RECIPE = 30
MAX_SHOPPING_ITEM = 200
MAX_SHOPPING_ITEMS_PER_CALL = 200


def strip_html(v) -> str:
    return re.sub(r"<[^>]+>", "", str(v)) if v else ""


def sanitize_str(v, max_len=500) -> str:
    return strip_html(v)[:max_len].strip()


def sanitize_list(lst, max_items=100, max_len=500) -> list[str]:
    if not isinstance(lst, list):
        lst = [lst]
    return [sanitize_str(x, max_len) for x in lst[:max_items] if x]


def json_col(raw, fallback):
    """
    Read a JSON text column without trusting it.

    Recipe rows carry JSON in TEXT columns. A malformed value — an older row, a
    hand-edited database, a restored backup — must degrade to an empty list
    rather than turn every read of that recipe into a 500.
    """
    if isinstance(raw, type(fallback)) and not isinstance(raw, str):
        return raw
    try:
        value = json.loads(raw) if raw else fallback
    except (TypeError, ValueError):
        return fallback
    return value if isinstance(value, type(fallback)) else fallback


def json_text(raw, fallback="[]") -> str:
    """Normalise a JSON column *for writing*: valid JSON in, valid JSON out."""
    if isinstance(raw, (list, dict)):
        return json.dumps(raw, ensure_ascii=False)
    try:
        json.loads(raw)
    except (TypeError, ValueError):
        return fallback
    return raw


def clamp_int(v, default=0, lo=0, hi=10_000) -> int:
    try:
        return max(lo, min(int(v), hi))
    except (TypeError, ValueError):
        return default
