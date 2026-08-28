# ── Stage 1: build the SolidJS frontend ─────────────────────────────────
FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
# Vite writes to ../static (see web/vite.config.ts)
RUN npm run build

# ── Stage 2: runtime (Python stdlib only) ───────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# No external Python dependencies needed - stdlib only
COPY server.py .
COPY lib/ lib/
COPY --from=web /static/ static/

# Create dirs for data
RUN mkdir -p /data/backups /data/logs

# Entrypoint with auto-restart
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8080

ENV DB_PATH=/data/recipes.db
ENV LOG_DIR=/data/logs
ENV BACKUP_DIR=/data/backups

ENTRYPOINT ["/entrypoint.sh"]
