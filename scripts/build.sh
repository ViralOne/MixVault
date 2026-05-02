#!/bin/bash
# Build recipes.db from HTML recipe files
# Usage: ./scripts/build.sh /path/to/recipe-html-folder

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
HTML_DIR="${1:-}"

if [ -z "$HTML_DIR" ]; then
    echo "Usage: ./scripts/build.sh /path/to/recipe-html-folder"
    echo ""
    echo "The folder should contain country subfolders with recipe HTML files:"
    echo "  Recipe Folder/Country/Collection/Recipe.html"
    exit 1
fi

if [ ! -d "$HTML_DIR" ]; then
    echo "Error: '$HTML_DIR' is not a directory"
    exit 1
fi

echo "═══ MixVault Database Builder ═══"
echo ""
echo "Source: $HTML_DIR"
echo "Output: $PROJECT_DIR/data/recipes.db"
echo ""

# Step 1: Parse HTML to JSON
echo "① Parsing HTML files to JSON..."
python3 "$SCRIPT_DIR/parse_recipes.py" "$HTML_DIR" > "$PROJECT_DIR/recipes.json"
COUNT=$(python3 -c "import json;print(len(json.load(open('$PROJECT_DIR/recipes.json'))))")
echo "   Found $COUNT recipes"

# Step 2: Build SQLite database
echo "② Building SQLite database..."
mkdir -p "$PROJECT_DIR/data"
cd "$PROJECT_DIR"
python3 "$SCRIPT_DIR/build_db.py"
echo "   Done"

# Step 3: Extract ingredient icons
echo "③ Extracting ingredient icons..."
python3 "$SCRIPT_DIR/build_icons.py" "$HTML_DIR"
echo "   Done"

# Cleanup
rm -f "$PROJECT_DIR/recipes.json"

echo ""
echo "✅ Database ready at data/recipes.db"
echo "   Run: docker compose up -d --build"
