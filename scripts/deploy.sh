#!/usr/bin/env bash
# shellcheck source-path=SCRIPTDIR
set -Eeuo pipefail
# shellcheck source=common.sh
source "$(dirname "$0")/common.sh"
version=${1:?Usage: deploy.sh FULL_COMMIT_SHA}
validate_sha "$version"
export IMAGE_TAG=$version
lock_deployment
load_state
trap on_failure ERR

log "Deploy candidate: $version"
compose config --quiet
# First deploy initializes an empty DB; subsequent deploys keep the same volume.
compose up -d --wait --wait-timeout 90 postgres
bash "$SCRIPT_ROOT/scripts/backup-db.sh"
log 'Pulling the two images built by CI.'
compose pull backend frontend
log 'Migrating with the candidate backend image; old app is still running.'
compose run --rm --no-deps backend alembic upgrade head

# Record the candidate before replacing containers. If startup/health/smoke fails,
# rollback still knows the last version that passed all checks.
if [[ "$version" != "$LAST_SUCCESSFUL_VERSION" ]]; then
  PREVIOUS_VERSION=$LAST_SUCCESSFUL_VERSION
fi
CURRENT_VERSION=$version
save_state
compose up -d --no-build --no-deps backend frontend
bash "$SCRIPT_ROOT/scripts/check-health.sh" "$version"
bash "$SCRIPT_ROOT/scripts/smoke-test.sh" "$version"
LAST_SUCCESSFUL_VERSION=$version
save_state
log "SUCCESS: deployed $version"
