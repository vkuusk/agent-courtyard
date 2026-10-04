#!/bin/sh
# Starts the hub: the Courtyard app runs this as its child, `make hub-start` without the
# app runs it detached. A PATH that finds docker and homebrew (the app's environment is
# nearly empty), this directory as cwd, the .env values, postgres up, then the hub itself
# from the project's own .venv (no uv needed at runtime).
set -eu
cd "$(dirname "$0")/.."

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

# Docker may still be starting (a start at login): wait for it rather than fail.
until docker info >/dev/null 2>&1; do
  echo "$(date '+%H:%M:%S') waiting for docker..."
  sleep 5
done
docker compose up -d --wait postgres >/dev/null

exec .venv/bin/courtyard-hub
