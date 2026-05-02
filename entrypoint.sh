#!/bin/sh
# Auto-restart on crash with backoff
MAX_RESTARTS=10
RESTART_DELAY=2
restarts=0

while true; do
    echo "[entrypoint] Starting server (attempt $((restarts+1)))..."
    python3 /app/server.py
    exit_code=$?
    
    if [ $exit_code -eq 0 ]; then
        echo "[entrypoint] Server exited cleanly."
        break
    fi
    
    restarts=$((restarts+1))
    if [ $restarts -ge $MAX_RESTARTS ]; then
        echo "[entrypoint] Max restarts ($MAX_RESTARTS) reached. Giving up."
        exit 1
    fi
    
    echo "[entrypoint] Server crashed (exit $exit_code). Restarting in ${RESTART_DELAY}s..."
    sleep $RESTART_DELAY
    RESTART_DELAY=$((RESTART_DELAY * 2))
    # Cap at 60s
    if [ $RESTART_DELAY -gt 60 ]; then RESTART_DELAY=60; fi
done
