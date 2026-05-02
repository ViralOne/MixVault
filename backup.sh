#!/bin/sh
# Manual backup script for recipes.db
# Usage: ./backup.sh [/path/to/recipes.db] [/path/to/backup/dir]

DB="${1:-./recipes.db}"
BACKUP_DIR="${2:-./backups}"
mkdir -p "$BACKUP_DIR"

TS=$(date +%Y%m%d_%H%M%S)
DEST="$BACKUP_DIR/recipes_${TS}.db"

# Use sqlite3 .backup for safe hot-copy
if command -v sqlite3 >/dev/null 2>&1; then
    sqlite3 "$DB" ".backup '$DEST'"
else
    cp "$DB" "$DEST"
fi

echo "Backup: $DEST ($(du -h "$DEST" | cut -f1))"

# Prune old backups (keep last 5)
ls -t "$BACKUP_DIR"/recipes_*.db 2>/dev/null | tail -n +6 | xargs rm -f 2>/dev/null
echo "Kept last 5 backups."
