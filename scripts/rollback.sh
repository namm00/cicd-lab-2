#!/usr/bin/env bash
# shellcheck source-path=SCRIPTDIR
set -Eeuo pipefail
# shellcheck source=common.sh
source "$(dirname "$0")/common.sh"
lock_deployment
load_state
target=${1:-}
if [[ -z "$target" ]]; then
  if [[ "$CURRENT_VERSION" != "$LAST_SUCCESSFUL_VERSION" && -n "$LAST_SUCCESSFUL_VERSION" ]]; then
    target=$LAST_SUCCESSFUL_VERSION
  else
    target=$PREVIOUS_VERSION
  fi
fi
[[ -n "$target" ]] || die 'No previous successful image. Supply a known compatible SHA or fix forward.'
validate_sha "$target"
[[ "$target" != "$CURRENT_VERSION" ]] || die 'Target is already CURRENT_VERSION.'
export IMAGE_TAG=$target
trap on_failure ERR
log "Rolling back images to $target. Database schema will stay unchanged."
compose pull backend frontend
old_successful=$LAST_SUCCESSFUL_VERSION
CURRENT_VERSION=$target
save_state
compose up -d --no-build --no-deps backend frontend
bash "$SCRIPT_ROOT/scripts/check-health.sh" "$target"
bash "$SCRIPT_ROOT/scripts/smoke-test.sh" "$target"
# Never make a failed candidate the default target of a later rollback.
if [[ "$old_successful" != "$target" ]]; then
  PREVIOUS_VERSION=$old_successful
else
  PREVIOUS_VERSION=
fi
LAST_SUCCESSFUL_VERSION=$target
save_state
log "SUCCESS: image rollback to $target (no Alembic downgrade)."
