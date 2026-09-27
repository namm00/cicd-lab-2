#!/usr/bin/env bash
# shellcheck source-path=SCRIPTDIR
set -Eeuo pipefail
# shellcheck source=common.sh
source "$(dirname "$0")/common.sh"
expected=${1:?Usage: check-health.sh EXPECTED_VERSION}
export IMAGE_TAG=$expected
url=http://127.0.0.1:${BACKEND_PORT:-8002}
attempts=${HEALTH_ATTEMPTS:-20}
delay=${HEALTH_DELAY:-3}
get_200() {
  local response status
  response=$(curl --silent --show-error --max-time 5 --write-out '\n%{http_code}' "$1") || return 1
  status=${response##*$'\n'}
  [[ "$status" == 200 ]] || { printf 'Expected HTTP 200, got %s\n' "$status" >&2; return 1; }
  printf '%s' "${response%$'\n'*}"
}
for ((attempt=1; attempt<=attempts; attempt++)); do
  if body=$(get_200 "$url/api/health") \
    && printf '%s' "$body" | compose exec -T backend python -c \
      'import json,sys; assert json.load(sys.stdin) == {"status":"ok"}' \
    && body=$(get_200 "$url/api/version") \
    && printf '%s' "$body" | compose exec -T backend python -c \
      'import json,sys; assert json.load(sys.stdin) == {"version":sys.argv[1]}' "$expected"; then
    log "Health and version passed: $expected"
    exit 0
  fi
  log "Health/version attempt $attempt/$attempts failed."
  sleep "$delay"
done
compose logs --tail=100 backend || true
die "Health/version did not pass for $expected"
