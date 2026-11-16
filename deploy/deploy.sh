#!/usr/bin/env bash
# Build and (re)start the production stack from the current checkout. Run on the VPS from the repo root:
#   ./deploy/deploy.sh            # update to the checked-out commit
#   ./deploy/deploy.sh --pull     # git pull first
set -euo pipefail
cd "$(dirname "$0")/.."

[ -f .env ] || { echo "Missing .env (copy .env.example)"; exit 1; }
if [ "${1:-}" = "--pull" ]; then git pull --ff-only; fi

export GIT_SHA
GIT_SHA="$(git rev-parse --short HEAD)"
COMPOSE=(docker compose -f deploy/docker-compose.prod.yml --env-file .env)
PROFILES=()
if grep -qE '^LITESTREAM_BUCKET=.+' .env; then PROFILES=(--profile backup); fi

"${COMPOSE[@]}" "${PROFILES[@]}" build
"${COMPOSE[@]}" "${PROFILES[@]}" run --rm --no-deps app cli check-config
"${COMPOSE[@]}" "${PROFILES[@]}" up -d --remove-orphans
"${COMPOSE[@]}" ps
echo "Deployed $GIT_SHA"
