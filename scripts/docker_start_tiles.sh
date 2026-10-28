#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

mkdir -p instance uploads uploads/datasets notebooks

TILE_GUNICORN_BIND="${TILE_GUNICORN_BIND:-0.0.0.0:8001}"
TILE_GUNICORN_WORKERS="${TILE_GUNICORN_WORKERS:-2}"
TILE_GUNICORN_THREADS="${TILE_GUNICORN_THREADS:-1}"
TILE_GUNICORN_TIMEOUT="${TILE_GUNICORN_TIMEOUT:-120}"
export INIT_DATABASE=0

echo "Starting XOpat tile Gunicorn on ${TILE_GUNICORN_BIND}"
GUNICORN_ARGS=(-w "$TILE_GUNICORN_WORKERS" -b "$TILE_GUNICORN_BIND" --timeout "$TILE_GUNICORN_TIMEOUT")
if [ "$TILE_GUNICORN_THREADS" != "1" ]; then
  GUNICORN_ARGS+=(--worker-class gthread --threads "$TILE_GUNICORN_THREADS")
fi

exec gunicorn "${GUNICORN_ARGS[@]}" 'app:create_app()'
