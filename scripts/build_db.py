#!/usr/bin/env python3
"""Import recipes.json into SQLite with FTS5 full-text search."""
import html, json, sqlite3
from pathlib import Path

DB = Path(__file__).parent.parent / "data" / "recipes.db"
SRC = Path(__file__).parent.parent / "recipes.json"

def ue(v):
    """html.unescape for str or list-of-str."""
    if isinstance(v, str): return html.unescape(v)
    if isinstance(v, list): return [html.unescape(s) if isinstance(s,str) else s for s in v]
    return v

def main():
    DB.unlink(missing_ok=True)
    db = sqlite3.connect(str(DB))
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")

    db.executescript("""
        CREATE TABLE recipes (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            country TEXT NOT NULL,
            lang TEXT NOT NULL,
            collection TEXT NOT NULL,
            image TEXT,
            total_time TEXT,
            yield TEXT,
            categories TEXT,
            ingredients TEXT,
            steps TEXT,
            nutrition TEXT,
            keywords TEXT
        );
        CREATE INDEX idx_country ON recipes(country);
        CREATE INDEX idx_lang ON recipes(lang);
        CREATE INDEX idx_collection ON recipes(collection);

        CREATE VIRTUAL TABLE recipes_fts USING fts5(
            id UNINDEXED, name, ingredients, keywords, collection, categories,
            content='recipes',
            content_rowid='rowid',
            tokenize='unicode61 remove_diacritics 2'
        );

        CREATE TABLE favorites (
            recipe_id TEXT PRIMARY KEY,
            added_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (recipe_id) REFERENCES recipes(id)
        );

        CREATE TABLE recent (
            recipe_id TEXT PRIMARY KEY,
            viewed_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (recipe_id) REFERENCES recipes(id)
        );
    """)

    print("Loading JSON...")
    recipes = json.loads(SRC.read_text())
    print(f"Importing {len(recipes)} recipes...")

    rows = []
    for r in recipes:
        rows.append((
            r["id"], ue(r["name"]), r["country"], r["lang"], ue(r["collection"]),
            r.get("image",""), r.get("totalTime",""), ue(r.get("yield","")),
            json.dumps(ue(r.get("categories",[])), ensure_ascii=False),
            json.dumps(ue(r.get("ingredients",[])), ensure_ascii=False),
            json.dumps(ue(r.get("steps",[])), ensure_ascii=False),
            json.dumps(r.get("nutrition",{}), ensure_ascii=False),
            ue(r.get("keywords","")),
        ))

    db.executemany(
        "INSERT OR IGNORE INTO recipes VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows
    )

    # Populate FTS index
    print("Building FTS index...")
    db.execute("""
        INSERT INTO recipes_fts(id, name, ingredients, keywords, collection, categories)
        SELECT id, name, ingredients, keywords, collection, categories FROM recipes
    """)

    db.commit()

    # Stats
    count = db.execute("SELECT count(*) FROM recipes").fetchone()[0]
    size_mb = DB.stat().st_size / 1024 / 1024
    print(f"Done: {count} recipes, {size_mb:.1f} MB database")
    db.close()

if __name__ == "__main__":
    main()
