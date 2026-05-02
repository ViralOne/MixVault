"""Recipe handlers: search, detail, meta, similar, favorites, translate, import, edit, delete, cookidoo, nutrition."""
import json, hashlib, re, time
import urllib.request
import urllib.parse
from ..config import log, LANG_NAMES, META_CACHE_TTL, GROQ_API_KEY, OPENROUTER_API_KEY
from ..db import get_db, _fts_escape, slim_row, slim_rows, full_row
from ..translate import _gtranslate
from ..ai import _ai_chat

_meta_cache = {"data": None, "ts": 0}


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
