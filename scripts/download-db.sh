#!/bin/bash
# Download recipes.db from GitHub Releases
# Usage: ./scripts/download-db.sh

set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DB_PATH="$PROJECT_DIR/data/recipes.db"
REPO="ViralOne/MixVault"

mkdir -p "$PROJECT_DIR/data"

if [ -f "$DB_PATH" ]; then
    echo "Database already exists at data/recipes.db"
    echo "Delete it first if you want to re-download."
    exit 0
fi

echo "Downloading recipes.db from GitHub Releases..."

# Try gh CLI first, fall back to curl
if command -v gh >/dev/null 2>&1; then
    gh release download --repo "$REPO" -p "recipes.db" -D "$PROJECT_DIR/data/"
else
    URL=$(curl -s "https://api.github.com/repos/$REPO/releases/latest" | grep -o '"browser_download_url": "[^"]*recipes.db"' | cut -d'"' -f4)
    if [ -z "$URL" ]; then
        echo "Error: Could not find recipes.db in latest release."
        echo "Download manually from: https://github.com/$REPO/releases"
        exit 1
    fi
    curl -L "$URL" -o "$DB_PATH"
fi

SIZE=$(du -h "$DB_PATH" | cut -f1)
echo "✅ Downloaded recipes.db ($SIZE) to data/"
