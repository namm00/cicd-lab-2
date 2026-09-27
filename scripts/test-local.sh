#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
trap 'docker compose -f compose.test.yaml down --volumes' EXIT
docker compose -f compose.test.yaml up --build --abort-on-container-exit --exit-code-from tests
