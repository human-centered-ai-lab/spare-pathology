#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

mkdir -p instance uploads uploads/datasets notebooks

XOPAT_NODE_PORT="${XOPAT_NODE_PORT:-9010}"
XOPAT_SERVER_URL="${XOPAT_SERVER_URL:-http://127.0.0.1:${XOPAT_NODE_PORT}}"
GUNICORN_BIND="${GUNICORN_BIND:-0.0.0.0:8000}"
GUNICORN_WORKERS="${GUNICORN_WORKERS:-1}"
GUNICORN_TIMEOUT="${GUNICORN_TIMEOUT:-300}"
ENABLE_JUPYTER="${ENABLE_JUPYTER:-0}"
JUPYTER_PORT="${JUPYTER_PORT:-8888}"
JUPYTER_TOKEN="${JUPYTER_TOKEN:-}"

export XOPAT_NODE_PORT XOPAT_SERVER_URL
export XOPAT_NODE_HOST=127.0.0.1
export INIT_DATABASE=0
flask --app app init-db

declare -a PIDS=()

cleanup() {
  for pid in "${PIDS[@]:-}"; do
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
  done
  wait 2>/dev/null || true
}

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

echo "Starting XOpat on 127.0.0.1:${XOPAT_NODE_PORT}"
(
  cd "${XOPAT_DIR:-$ROOT/vendor/xopat}"
  XOPAT_ENV="$ROOT/config/xopat-env.json" \
  XOPAT_NODE_PORT="$XOPAT_NODE_PORT" \
  exec node index.js
) &
PIDS+=("$!")

if [ "$ENABLE_JUPYTER" = "1" ]; then
  : "${JUPYTER_TOKEN:?Set JUPYTER_TOKEN when enabling notebooks}"
  echo "Starting Jupyter on port ${JUPYTER_PORT}"
  jupyter notebook \
    --no-browser \
    --ip=0.0.0.0 \
    --port="$JUPYTER_PORT" \
    --IdentityProvider.token="$JUPYTER_TOKEN" \
    --ServerApp.base_url=/jupyter/ \
    --notebook-dir="${NOTEBOOKS_DIR:-$ROOT/notebooks}" &
  PIDS+=("$!")
fi

echo "Starting Gunicorn on ${GUNICORN_BIND}"
GUNICORN_ARGS=(-w "$GUNICORN_WORKERS" -b "$GUNICORN_BIND" --timeout "$GUNICORN_TIMEOUT")
gunicorn "${GUNICORN_ARGS[@]}" 'app:create_app()' &
PIDS+=("$!")

set +e
wait -n "${PIDS[@]}"
status=$?
set -e

exit "$status"
