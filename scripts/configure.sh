#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ -e .env ]; then
  echo '.env already exists; keeping the existing configuration.'
  exit 0
fi
command -v openssl >/dev/null || { echo 'OpenSSL is required to generate credentials.' >&2; exit 1; }
umask 077
mkdir -p instance uploads notebooks
runtime_uid="$(id -u)"
runtime_gid="$(id -g)"
if [ "$runtime_uid" = '0' ]; then
  runtime_uid=10001
  runtime_gid=10001
  chown "$runtime_uid:$runtime_gid" instance uploads notebooks
fi
admin_password="$(openssl rand -hex 24)"
secret_key="$(openssl rand -hex 32)"
jupyter_token="$(openssl rand -hex 24)"
(set -o noclobber; cat > .env <<ENV
ADMIN_EMAIL=admin
ADMIN_PASSWORD=$admin_password
SECRET_KEY=$secret_key
SPARE_UID=$runtime_uid
SPARE_GID=$runtime_gid
BIND_ADDRESS=127.0.0.1
PORT=8000
SESSION_COOKIE_SECURE=0
SEED_DEMO_DATA=0
ENABLE_JUPYTER=0
JUPYTER_TOKEN=$jupyter_token
ENV
)
printf 'Created .env and persistent storage directories.\nAdmin login: admin\nPassword: %s\nKeep .env private; it contains your credentials.\n' "$admin_password"
