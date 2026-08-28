"""Recipe handlers: search, detail, meta, similar, favorites, translate, import, edit, delete, cookidoo, nutrition."""
import json, hashlib, re, time
import urllib.request
import urllib.parse
from ..config import LANG_NAMES, META_CACHE_TTL
from ..db import (get_db, _fts_escape, slim_row, slim_rows, full_row, find_recipe,
                  search_user_recipes, fts_index, fts_unindex)
from ..users import users_exist
from ..translate import _gtranslate
from ..ai import _ai_chat

_meta_cache = {"data": None, "ts": 0}


def _strip_html(v):
    return re.sub(r"<[^>]+>", "", str(v)) if v else ""


def sanitize_str(v, max_len=500):
    return _strip_html(v)[:max_len].strip()


def sanitize_list(lst, max_items=100, max_len=500):
    if not isinstance(lst, list):
        lst = [lst]
    return [sanitize_str(x, max_len) for x in lst[:max_items] if x]


def _int_param(params, name, default, lo, hi):
    """Query params are user input; a bad one is a 400, not a 500."""
    raw = params.get(name, [str(default)])[0]
    try:
        return max(lo, min(int(raw), hi))
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a whole number")


def _library_is_writable(self):
    """Shared recipes are read-only once vaults exist — nobody owns them."""
    return not users_exist()


def _search(self, params):
    """
    Browse/search the shared library plus this vault's private recipes.

    The library is indexed with FTS5; private recipes are never added to that
    index (it lives in the shareable recipes.db), so they are matched with a
    LIKE pass and placed first — there are only ever a handful.
    """
    db = get_db()
    uid = self.user_id
    q = params.get("q",[""])[0].strip()
    country = params.get("country",[""])[0]
    lang = params.get("lang",[""])[0]
    col = params.get("collection",[""])[0]
    fav = params.get("favorites",[""])[0]
    tag = params.get("tag",[""])[0]
    random = params.get("random",[""])[0]
    try:
        limit = _int_param(params, "limit", 60, 1, 200)
        offset = _int_param(params, "offset", 0, 0, 10_000_000)
    except ValueError as e:
        return self._json({"error": str(e)}, 400)

    wheres, args = [], []
    if country:
        wheres.append("r.country=?"); args.append(country)
    if lang:
        wheres.append("r.lang=?"); args.append(lang)
    if col:
        wheres.append("r.collection=?"); args.append(col)
    if fav == "1":
        wheres.append("r.id IN (SELECT recipe_id FROM vault.favorites WHERE user_id=?)")
        args.append(uid)
    if tag:
        wheres.append("r.id IN (SELECT recipe_id FROM vault.recipe_tags WHERE user_id=? AND tag=?)")
        args += [uid, tag]

    mine = search_user_recipes(db, uid, query=q, country=country, lang=lang,
                              collection=col, favorites=fav == "1", tag=tag)

    if random == "1":
        where_sql = " WHERE "+" AND ".join(wheres) if wheres else ""
        rows = db.execute(
            f"SELECT r.* FROM visible_recipes r{where_sql}{' AND' if wheres else ' WHERE'}"
            f" (r.owner='' OR r.owner=?) ORDER BY RANDOM() LIMIT 1", args + [uid]).fetchall()
        return self._json({"total": len(rows), "offset": 0, "limit": 1,
                           "recipes": slim_rows(rows, uid)})

    if q:
        fts_q = _fts_escape(q)
        if not fts_q:
            lib_count, lib_rows = 0, []
        else:
            where_sql = (" AND " + " AND ".join(wheres)) if wheres else ""
            lib_count = db.execute(
                "SELECT count(*) FROM recipes r JOIN recipes_fts f ON r.id=f.id"
                f" WHERE recipes_fts MATCH ?{where_sql}", [fts_q]+args).fetchone()[0]
            # Skip whatever the private matches already filled on earlier pages.
            lib_offset = max(0, offset - len(mine))
            lib_rows = db.execute(
                "SELECT r.* FROM recipes r JOIN recipes_fts f ON r.id=f.id"
                f" WHERE recipes_fts MATCH ?{where_sql} ORDER BY rank LIMIT ? OFFSET ?",
                [fts_q]+args+[limit, lib_offset]).fetchall()
    else:
        where_sql = " WHERE "+" AND ".join(wheres) if wheres else ""
        lib_count = db.execute(f"SELECT count(*) FROM recipes r{where_sql}", args).fetchone()[0]
        lib_offset = max(0, offset - len(mine))
        lib_rows = db.execute(
            f"SELECT r.* FROM recipes r{where_sql} LIMIT ? OFFSET ?",
            args+[limit, lib_offset]).fetchall()

    # Private recipes occupy the first slots of the result sequence.
    page = list(mine[offset:offset+limit]) if offset < len(mine) else []
    page += list(lib_rows)[:limit - len(page)]
    self._json({"total": lib_count + len(mine), "offset": offset, "limit": limit,
                "recipes": slim_rows(page, uid)})

def _recipe(self, rid):
    db = get_db()
    uid = self.user_id
    row = find_recipe(db, rid, uid)
    if row:
        # Track recent view
        db.execute("INSERT OR REPLACE INTO vault.recent(user_id,recipe_id) VALUES(?,?)", [uid, rid])
        db.commit()
        data = full_row(row)
        # Shared library recipes are not editable once vaults exist.
        data["private"] = row["source"] == "vault"
        data["editable"] = data["private"] or _library_is_writable(self)
        data["is_favorite"] = db.execute("SELECT 1 FROM vault.favorites WHERE user_id=? AND recipe_id=?",
                                         [uid, rid]).fetchone() is not None
        note_row = db.execute("SELECT note FROM vault.recipe_notes WHERE user_id=? AND recipe_id=?",
                              [uid, rid]).fetchone()
        data["note"] = note_row["note"] if note_row else ""
        cook_count = db.execute("SELECT count(*) FROM vault.cooking_history WHERE user_id=? AND recipe_id=?",
                                [uid, rid]).fetchone()[0]
        data["cook_count"] = cook_count
        self._json(data)
    else:
        self._json({"error":"not found"}, 404)

def _meta(self, params=None):
    now = time.time()
    db = get_db()
    # Cache only the library figures; favourites are per-vault.
    fav_count = db.execute("SELECT count(*) FROM vault.favorites WHERE user_id=?",
                           [self.user_id]).fetchone()[0]
    if _meta_cache["data"] and now - _meta_cache["ts"] < META_CACHE_TTL:
        return self._json({**_meta_cache["data"], "favorites": fav_count})
    total = db.execute("SELECT count(*) FROM recipes").fetchone()[0]
    countries = [{"country":r[0],"lang":r[1],"count":r[2]}
        for r in db.execute("SELECT country, lang, count(*) FROM recipes"
                            " GROUP BY country ORDER BY count(*) DESC")]
    lang_rows = db.execute("SELECT lang, count(*) FROM recipes"
                           " GROUP BY lang ORDER BY count(*) DESC").fetchall()
    languages = [{"lang":r[0],"name":LANG_NAMES.get(r[0],r[0]),"count":r[1]} for r in lang_rows]
    result = {"total":total,"countries":countries,"languages":languages}
    _meta_cache["data"] = result
    _meta_cache["ts"] = now
    self._json({**result, "favorites": fav_count})

def _similar(self, rid, params):
    db = get_db()
    try:
        limit = _int_param(params, "limit", 6, 1, 20)
    except ValueError as e:
        return self._json({"error": str(e)}, 400)
    row = find_recipe(db, rid, self.user_id)
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
    self._json({"recipes": slim_rows(unique, self.user_id)})

def _favorites_list(self, params):
    db = get_db()
    rows = db.execute("""
        SELECT r.* FROM visible_recipes r
        JOIN vault.favorites f ON r.id=f.recipe_id
        WHERE f.user_id=? AND (r.owner='' OR r.owner=?)
        ORDER BY f.added_at DESC
    """, [self.user_id, self.user_id]).fetchall()
    self._json({"total":len(rows),"offset":0,"limit":len(rows),"recipes":slim_rows(rows, self.user_id)})

def _translate(self, rid, req):
    tgt = req.get("lang", "en")
    db = get_db()
    row = find_recipe(db, rid, self.user_id)
    if not row:
        return self._json({"error": "not found"}, 404)
    src = row["lang"]
    if src == tgt:
        return self._json({"error": "same language", "id": rid})
    # Check if translation already exists
    new_id = hashlib.md5(f"{self.user_id}:{rid}:{tgt}".encode()).hexdigest()[:12]
    existing = db.execute("SELECT id FROM vault.user_recipes WHERE id=?", [new_id]).fetchone()
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
        "INSERT OR IGNORE INTO vault.user_recipes(id,owner,name,country,lang,collection,image,total_time,yield,categories,ingredients,steps,nutrition,keywords) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (new_id, self.user_id, name, row["country"], tgt,
         row["collection"], row["image"], row["total_time"], yld,
         json.dumps(cats, ensure_ascii=False),
         json.dumps(ings, ensure_ascii=False),
         json.dumps(steps, ensure_ascii=False),
         row["nutrition"], kw)
    )
    db.commit()
    self._json({"id": new_id, "cached": False})

def _recipe_import(self, req):
    """Import a custom recipe."""
    required = ["name", "ingredients", "steps"]
    for f in required:
        if not req.get(f):
            return self._json({"error": f"missing field: {f}"}, 400)
    name = sanitize_str(req["name"], 200)
    if not name:
        return self._json({"error": "name is empty after sanitization"}, 400)
    ingredients = sanitize_list(req["ingredients"])
    steps = sanitize_list(req["steps"], max_items=50, max_len=2000)
    if not ingredients or not steps:
        return self._json({"error": "ingredients and steps must be non-empty lists"}, 400)

    db = get_db()
    # Include the owner so two vaults can import the same recipe name.
    rid = hashlib.md5((self.user_id + ":" + name).encode()).hexdigest()[:12]
    if db.execute("SELECT 1 FROM vault.user_recipes WHERE id=? AND owner=?",
                  [rid, self.user_id]).fetchone():
        return self._json({"error": "recipe already exists", "id": rid}, 409)
    db.execute(
        "INSERT INTO vault.user_recipes(id,owner,name,country,lang,collection,image,total_time,yield,categories,ingredients,steps,nutrition,keywords) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (rid, self.user_id, name, sanitize_str(req.get("country","Custom"), 50), sanitize_str(req.get("lang","en"), 5),
         sanitize_str(req.get("collection","My Recipes"), 100), sanitize_str(req.get("image",""), 500),
         sanitize_str(req.get("totalTime",""), 20), sanitize_str(req.get("yield",""), 50),
         json.dumps(sanitize_list(req.get("categories",[]), 20, 100), ensure_ascii=False),
         json.dumps(ingredients, ensure_ascii=False),
         json.dumps(steps, ensure_ascii=False),
         json.dumps(req.get("nutrition",{}) if isinstance(req.get("nutrition"), dict) else {}, ensure_ascii=False),
         sanitize_str(req.get("keywords",""), 500))
    )
    db.commit()
    self._json({"ok": True, "id": rid})

def _recipe_edit(self, rid, req):
    db = get_db()
    row = find_recipe(db, rid, self.user_id)
    if not row:
        return self._json({"error": "not found"}, 404)
    is_library = row["source"] == "library"
    if is_library and not _library_is_writable(self):
        # Shared recipes belong to everyone; a single vault must not rewrite them.
        return self._json({"error": "shared library recipes are read-only"}, 403)

    name = sanitize_str(req.get("name", row["name"]), 200) or row["name"]
    ingredients = sanitize_list(req.get("ingredients") or json.loads(row["ingredients"]))
    steps = sanitize_list(req.get("steps") or json.loads(row["steps"]), max_items=50, max_len=2000)
    if not ingredients or not steps:
        return self._json({"error": "ingredients and steps must be non-empty lists"}, 400)
    image = sanitize_str(req.get("image", row["image"]), 500)
    yld = sanitize_str(req.get("yield", row["yield"]), 50)
    total_time = sanitize_str(req.get("totalTime", row["total_time"]), 20)
    categories = sanitize_list(req.get("categories") or json.loads(row["categories"]), 20, 100)
    keywords = sanitize_str(req.get("keywords", row["keywords"]), 500)

    table = "recipes" if is_library else "vault.user_recipes"
    if is_library:
        fts_unindex(db, rid)  # must happen while the old content row is still there
    db.execute(
        f"UPDATE {table} SET name=?,image=?,total_time=?,yield=?,categories=?,ingredients=?,steps=?,keywords=?"
        " WHERE id=?",
        [name, image, total_time, yld, json.dumps(categories, ensure_ascii=False),
         json.dumps(ingredients, ensure_ascii=False), json.dumps(steps, ensure_ascii=False), keywords, rid])
    if is_library:
        fts_index(db, rid)
    db.commit()
    self._json({"ok": True})

def _recipe_delete(self, rid):
    db = get_db()
    row = find_recipe(db, rid, self.user_id)
    if not row:
        return self._json({"error": "not found"}, 404)
    if row["source"] == "library":
        if not _library_is_writable(self):
            return self._json({"error": "shared library recipes are read-only"}, 403)
        fts_unindex(db, rid)
        db.execute("DELETE FROM recipes WHERE id=?", [rid])
        _meta_cache["ts"] = 0
    else:
        db.execute("DELETE FROM vault.user_recipes WHERE id=? AND owner=?", [rid, self.user_id])
    # Only this vault's traces of the recipe — never anyone else's.
    for table in ("favorites", "recipe_notes", "recipe_tags", "cooking_history", "recent"):
        db.execute(f"DELETE FROM vault.{table} WHERE user_id=? AND recipe_id=?", [self.user_id, rid])
    db.execute("DELETE FROM vault.cooking_state WHERE user_id=? AND recipe_id=?", [self.user_id, rid])
    db.commit()
    self._json({"ok": True})

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
    existing = db.execute(
        "SELECT id FROM vault.user_recipes WHERE owner=? AND name=? AND lang=?",
        [self.user_id, name, lang]).fetchone()
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
    rid = hashlib.md5(f"{self.user_id}:{name}:{lang}".encode()).hexdigest()[:12]
    nut = {"calories": nutrition.get("calories",""), "protein": nutrition.get("proteinContent",""),
           "carbs": nutrition.get("carbohydrateContent",""), "fat": nutrition.get("fatContent","")}
    db.execute(
        "INSERT OR IGNORE INTO vault.user_recipes(id,owner,name,country,lang,collection,image,total_time,yield,categories,ingredients,steps,nutrition,keywords) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (rid, self.user_id, name, "Imported", lang, "Cookidoo Import", image, total_time, yld,
         json.dumps(categories, ensure_ascii=False), json.dumps(ingredients, ensure_ascii=False),
         json.dumps(steps, ensure_ascii=False), json.dumps(nut, ensure_ascii=False), keywords))
    db.commit()
    self._json({"id": rid, "exists": False, "name": name, "steps_generated": len(steps)})

def _nutrition_search(self, params):
    """Filter recipes by nutritional values."""
    db = get_db()

    def num(name):
        raw = params.get(name, [""])[0]
        if not raw:
            return None
        try:
            return float(raw)
        except ValueError:
            raise ValueError(f"{name} must be a number")

    try:
        max_cal, min_protein = num("max_calories"), num("min_protein")
        max_carbs, max_fat = num("max_carbs"), num("max_fat")
        limit = _int_param(params, "limit", 30, 1, 100)
    except ValueError as e:
        return self._json({"error": str(e)}, 400)
    lang = params.get("lang", [""])[0]

    # SQLite JSON extraction on nutrition field
    wheres = ["json_extract(r.nutrition, '$.calories') != ''", "(r.owner='' OR r.owner=?)"]
    args = [self.user_id]
    if max_cal is not None:
        wheres.append("CAST(REPLACE(json_extract(r.nutrition, '$.calories'), ' kcal', '') AS REAL) <= ?")
        args.append(max_cal)
    if min_protein is not None:
        wheres.append("CAST(REPLACE(REPLACE(json_extract(r.nutrition, '$.protein'), ' g', ''), ',', '.') AS REAL) >= ?")
        args.append(min_protein)
    if max_carbs is not None:
        wheres.append("CAST(REPLACE(REPLACE(json_extract(r.nutrition, '$.carbs'), ' g', ''), ',', '.') AS REAL) <= ?")
        args.append(max_carbs)
    if max_fat is not None:
        wheres.append("CAST(REPLACE(REPLACE(json_extract(r.nutrition, '$.fat'), ' g', ''), ',', '.') AS REAL) <= ?")
        args.append(max_fat)
    if lang:
        wheres.append("r.lang=?")
        args.append(lang)
    where_sql = " AND ".join(wheres)
    rows = db.execute(f"SELECT r.* FROM visible_recipes r WHERE {where_sql} LIMIT ?",
                      args + [limit]).fetchall()
    self._json({"total": len(rows), "recipes": slim_rows(rows, self.user_id)})
