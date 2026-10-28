#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
XOPAT_DIR="$ROOT/vendor/xopat"
OPENSEADRAGON_DIR="$XOPAT_DIR/openseadragon"
OPENSEADRAGON_BUILD="$OPENSEADRAGON_DIR/build/openseadragon/openseadragon.js"
XOPAT_UI_BUILD="$XOPAT_DIR/ui/index.js"
OPENSEADRAGON_REVISION=0866e108e9a383e173180ad639232c808f82f7d2
export CYPRESS_INSTALL_BINARY=0
export PUPPETEER_SKIP_DOWNLOAD=1

npm_install() {
  local dir="$1"
  if [ -f "$dir/package-lock.json" ]; then
    (cd "$dir" && npm ci)
  else
    (cd "$dir" && npm install)
  fi
}

if [ ! -d "$XOPAT_DIR" ]; then
  echo "XOpat vendor copy not found at $XOPAT_DIR" >&2
  exit 1
fi

if [ ! -d "$XOPAT_DIR/node_modules" ]; then
  npm_install "$XOPAT_DIR"
fi

if [ ! -f "$XOPAT_UI_BUILD" ]; then
  (cd "$XOPAT_DIR" && npx grunt buildUI)
fi

if [ ! -d "$OPENSEADRAGON_DIR" ]; then
  git init "$OPENSEADRAGON_DIR"
  git -C "$OPENSEADRAGON_DIR" remote add origin https://github.com/RationAI/openseadragon.git
  git -C "$OPENSEADRAGON_DIR" fetch --depth 1 origin "$OPENSEADRAGON_REVISION"
  git -C "$OPENSEADRAGON_DIR" checkout --detach FETCH_HEAD
fi

if [ ! -d "$OPENSEADRAGON_DIR/node_modules" ]; then
  npm_install "$OPENSEADRAGON_DIR"
fi

if [ ! -f "$OPENSEADRAGON_BUILD" ]; then
  (cd "$OPENSEADRAGON_DIR" && npx grunt build)
fi
