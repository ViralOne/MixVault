"""AI-powered handlers: search, recipe creator, image search, substitutions."""
import json, re, time
import urllib.request
import urllib.parse
from ..config import log, GROQ_API_KEY, OPENROUTER_API_KEY
from ..db import get_db, slim_row
from ..ai import _ai_chat, _ai_rate, AI_RATE_LIMIT, AI_RATE_WINDOW


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
