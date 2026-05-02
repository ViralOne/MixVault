#!/usr/bin/env python3
"""Parse recipe HTML files into JSON. Usage: python3 parse_recipes.py /path/to/html-folder > recipes.json"""
import json, re, hashlib, sys
from pathlib import Path

SOURCE = Path(sys.argv[1]) if len(sys.argv) > 1 else None

if not SOURCE:
    print("Usage: python3 parse_recipes.py /path/to/html-folder", file=sys.stderr)
    sys.exit(1)

COUNTRY_LANG = {
    "Argentina": "es", "Australia": "en", "Austria": "de", "Belgium": "fr",
    "Brazil": "pt", "Canada": "en", "Chile": "es", "China": "zh",
    "Colombia": "es", "Cyprus": "el", "Czech Republic": "cs", "Denmark": "da",
    "France": "fr", "Germany": "de", "Greece": "el", "Guatemala": "es",
    "Hungary": "hu", "Iceland": "is", "Indonesia": "id", "Italy": "it",
    "Malaysia": "ms", "Mexico": "es", "Netherland": "nl", "Norway": "no",
    "Panama": "es", "Paraguay": "es", "Peru": "es", "Philippines": "en",
    "Poland": "pl", "Portugal": "pt", "Romania": "ro", "Saudi Arabia": "ar",
    "Singapore": "zh", "Spain": "es", "Sweden": "sv", "Switzerland": "de",
    "Taiwan": "zh", "Turkey": "tr", "United Kingdom": "en", "USA": "en",
    "Vietnam": "vi",
}

LANG_NAMES = {
    "en": "English", "de": "German", "fr": "French", "it": "Italian",
    "es": "Spanish", "pt": "Portuguese", "pl": "Polish", "cs": "Czech",
    "ro": "Romanian", "nl": "Dutch", "da": "Danish", "sv": "Swedish",
    "no": "Norwegian", "hu": "Hungarian", "tr": "Turkish", "el": "Greek",
    "zh": "Chinese", "id": "Indonesian", "ms": "Malay", "is": "Icelandic",
    "ar": "Arabic", "vi": "Vietnamese",
}

def parse_file(path: Path, country: str, collection: str) -> dict | None:
    try:
        html = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None
    m = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL)
    if not m:
        return None
    try:
        r = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None
    if r.get("@type") != "Recipe":
        return None
    steps = []
    for s in r.get("recipeInstructions", []):
        text = s.get("text", "") if isinstance(s, dict) else str(s)
        text = re.sub(r"<[^>]+>", "", text)
        if text.strip():
            steps.append(text.strip())
    if not steps:
        return None
    nut = r.get("nutrition", {})
    lang = COUNTRY_LANG.get(country, "en")
    name = r.get("name", path.stem)
    # Unique ID from country + collection + name
    uid = hashlib.md5(f"{country}/{collection}/{name}".encode()).hexdigest()[:12]
    return {
        "id": uid,
        "name": name,
        "country": country,
        "lang": lang,
        "collection": collection,
        "image": r.get("image", ""),
        "totalTime": r.get("totalTime", ""),
        "yield": r.get("recipeYield", ""),
        "categories": r.get("recipeCategory", []),
        "ingredients": r.get("recipeIngredient", []),
        "steps": steps,
        "nutrition": {
            "calories": nut.get("calories", ""),
            "protein": nut.get("proteinContent", ""),
            "carbs": nut.get("carbohydrateContent", ""),
            "fat": nut.get("fatContent", ""),
        },
        "keywords": r.get("keywords", ""),
    }

def main():
    if not SOURCE.exists():
        print(f"Error: {SOURCE} not found", file=sys.stderr)
        sys.exit(1)
    recipes = []
    countries = sorted(d for d in SOURCE.iterdir() if d.is_dir())
    for ci, country_dir in enumerate(countries):
        country = country_dir.name
        collections = sorted(d for d in country_dir.iterdir() if d.is_dir())
        count = 0
        for col_dir in collections:
            for f in col_dir.glob("*.html"):
                r = parse_file(f, country, col_dir.name)
                if r:
                    recipes.append(r)
                    count += 1
        print(f"[{ci+1}/{len(countries)}] {country}: {count} recipes", file=sys.stderr)
    print(json.dumps(recipes, ensure_ascii=False))
    print(f"\nTotal: {len(recipes)} recipes", file=sys.stderr)

if __name__ == "__main__":
    main()
