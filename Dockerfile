FROM python:3.12-slim

WORKDIR /app

# No external dependencies needed - stdlib only
COPY server.py .
COPY static/ static/

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
