#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
./scripts/configure.sh
set -a
source .env
set +a
if [ ! -d .venv ]; then python3 -m venv .venv; fi
source .venv/bin/activate
pip install -r requirements-dev.txt
(cd frontend && npm ci)
./scripts/setup_xopat.sh
export INIT_DATABASE=0
flask --app app init-db
declare -a pids=()
cleanup() {
  for pid in "${pids[@]}"; do kill "$pid" 2>/dev/null || true; done
  wait || true
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
(cd vendor/xopat && XOPAT_NODE_HOST=127.0.0.1 XOPAT_ENV="$PWD/../../config/xopat-env.json" exec node index.js) &
pids+=("$!")
flask --app app run --host 127.0.0.1 --port 5000 --debug --no-reload &
pids+=("$!")
if [ "${ENABLE_JUPYTER:-0}" = '1' ]; then
  pip install -r requirements-notebook.txt
  jupyter notebook --no-browser --ip=127.0.0.1 --port=8888 \
    --IdentityProvider.token="$JUPYTER_TOKEN" --ServerApp.base_url=/jupyter/ \
    --notebook-dir="$PWD/notebooks" &
  pids+=("$!")
fi
(cd frontend && exec node node_modules/vite/bin/vite.js --host 127.0.0.1) &
pids+=("$!")
echo 'SPaRE development server: http://localhost:5173'
wait -n "${pids[@]}"
