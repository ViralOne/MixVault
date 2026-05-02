#!/usr/bin/env python3
"""Extract ingredient icon mappings from recipe HTML files and store in DB."""
import re, json, sqlite3, sys
from pathlib import Path
from collections import Counter

HTML_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else None
DB_PATH = Path(__file__).parent.parent / "data" / "recipes.db"

if not HTML_DIR:
    print("Usage: python3 build_icons.py /path/to/html-folder", file=sys.stderr)
    sys.exit(1)

def extract_icons():
    """Extract ingredient name → icon ID mappings from all HTML files."""
    mapping = {}  # normalized_name -> icon_id (most common wins)
    counts = {}   # normalized_name -> Counter of icon_ids
    
    for html_file in HTML_DIR.rglob("*.html"):
        html = html_file.read_text(errors='ignore')
        # Match icon ID followed by ingredient name
        pairs = re.findall(
            r'ingredient_icons/(\d+).*?recipe-ingredient__name[^>]*>\s*([^<]+)',
            html, re.DOTALL
        )
        for icon_id, name in pairs:
            name = name.strip().lower()
            # Normalize: remove quantities, amounts
            name = re.sub(r'^\d+[\s.,/]*\d*\s*(g|kg|ml|l|tsp|tbsp|cup|oz|lb|piece|pieces)?\s*', '', name)
            name = name.strip()
            if not name or len(name) < 2:
                continue
            if name not in counts:
                counts[name] = Counter()
            counts[name][icon_id] += 1
    
    # Pick most common icon for each ingredient
    for name, counter in counts.items():
        mapping[name] = counter.most_common(1)[0][0]
    
    return mapping

def save_to_db(mapping):
    db = sqlite3.connect(str(DB_PATH))
    db.execute("""CREATE TABLE IF NOT EXISTS ingredient_icons (
        name TEXT PRIMARY KEY,
        icon_id INTEGER NOT NULL
    )""")
    db.execute("DELETE FROM ingredient_icons")
    db.executemany("INSERT INTO ingredient_icons(name, icon_id) VALUES(?,?)",
                   [(k, int(v)) for k, v in mapping.items()])
    db.commit()
    print(f"Saved {len(mapping)} ingredient→icon mappings to DB")
    db.close()

if __name__ == "__main__":
    print("Extracting icons from HTML files...")
    mapping = extract_icons()
    print(f"Found {len(mapping)} unique ingredient→icon mappings")
    # Show some examples
    for name, icon_id in list(mapping.items())[:10]:
        print(f"  {name} → {icon_id}")
    save_to_db(mapping)
