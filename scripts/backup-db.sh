#!/usr/bin/env bash
# shellcheck source-path=SCRIPTDIR
set -Eeuo pipefail
# shellcheck source=common.sh
source "$(dirname "$0")/common.sh"
umask 077
mkdir -p "$DEPLOY_DIR/backups"
temporary=$(mktemp "$DEPLOY_DIR/backups/$(date -u +%Y%m%dT%H%M%SZ).XXXXXX")
backup=$temporary.dump
trap 'rm -f "$backup.partial"' EXIT
mv "$temporary" "$backup.partial"
log 'Creating PostgreSQL backup before migration.'
compose exec -T postgres pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom > "$backup.partial"
[[ -s "$backup.partial" ]] || die 'pg_dump produced an empty backup.'
compose exec -T postgres pg_restore --list < "$backup.partial" > /dev/null
mv "$backup.partial" "$backup"
log "Backup saved: $backup"
