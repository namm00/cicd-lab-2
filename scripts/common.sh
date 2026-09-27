#!/usr/bin/env bash
# Shared helpers. This file is sourced, never run by itself.
set -Eeuo pipefail

SCRIPT_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
DEPLOY_DIR=${DEPLOY_DIR:-$SCRIPT_ROOT}
ENV_FILE=${ENV_FILE:-$DEPLOY_DIR/.env.prod}
COMPOSE_FILE=${COMPOSE_FILE:-$SCRIPT_ROOT/compose.prod.yaml}
COMPOSE_PROJECT_NAME=${COMPOSE_PROJECT_NAME:-cicd-lab-2-prod}
STATE_DIR=$DEPLOY_DIR/state

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
log() { printf '[%s] %s\n' "$(date -u +%FT%TZ)" "$*"; }
[[ -f "$ENV_FILE" ]] || die "Missing $ENV_FILE; copy and configure the example first."
# Both Compose and Bash read this trusted, operator-owned file. Never download it.
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

compose() {
  docker compose --project-name "$COMPOSE_PROJECT_NAME" --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

validate_sha() { [[ "$1" =~ ^[0-9a-f]{40}$ ]] || die "Expected a full 40-character lowercase commit SHA: $1"; }

lock_deployment() {
  mkdir -p "$STATE_DIR"
  exec 9>"$DEPLOY_DIR/deploy.lock"
  flock -n 9 || die 'Another deploy/rollback is running.'
}

load_state() {
  CURRENT_VERSION='' PREVIOUS_VERSION='' LAST_SUCCESSFUL_VERSION=''
  if [[ -f "$STATE_DIR/versions.env" ]]; then
    while IFS='=' read -r key value; do
      [[ -z "$value" ]] || validate_sha "$value"
      case "$key" in
        CURRENT_VERSION) CURRENT_VERSION=$value ;;
        PREVIOUS_VERSION) PREVIOUS_VERSION=$value ;;
        LAST_SUCCESSFUL_VERSION) LAST_SUCCESSFUL_VERSION=$value ;;
        *) die "Unknown state key: $key" ;;
      esac
    done < "$STATE_DIR/versions.env"
  fi
}

save_state() {
  local temporary
  temporary=$(mktemp "$STATE_DIR/.versions.XXXXXX")
  printf 'CURRENT_VERSION=%s\nPREVIOUS_VERSION=%s\nLAST_SUCCESSFUL_VERSION=%s\n' \
    "$CURRENT_VERSION" "$PREVIOUS_VERSION" "$LAST_SUCCESSFUL_VERSION" > "$temporary"
  mv "$temporary" "$STATE_DIR/versions.env"
}

failure_logs() {
  log 'Deployment failed. Inspect /api/version and state/versions.env before recovery.'
  compose ps || true
  compose logs --tail=80 backend frontend postgres || true
}

on_failure() {
  local code=$?
  trap - ERR
  failure_logs
  exit "$code"
}
