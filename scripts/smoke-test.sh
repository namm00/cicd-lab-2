#!/usr/bin/env bash
# shellcheck source-path=SCRIPTDIR
set -Eeuo pipefail
# shellcheck source=common.sh
source "$(dirname "$0")/common.sh"
expected=${1:?Usage: smoke-test.sh EXPECTED_VERSION}
export IMAGE_TAG=$expected
# Host port check, then real HTTP operations through the Docker service network.
status=$(curl --fail --silent --show-error --retry 5 --retry-connrefused --max-time 10 \
  --output /dev/null --write-out '%{http_code}' "http://127.0.0.1:${FRONTEND_PORT:-8082}/")
[[ "$status" == 200 ]] || die "Frontend returned HTTP $status, expected 200."
compose exec -T backend python -m app.smoke http://frontend:8080 "$expected"
