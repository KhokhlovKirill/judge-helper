#!/usr/bin/env bash
set -euo pipefail
docker cp ci/backup.sh "$DB_CONTAINER:/tmp/backup.sh"
docker exec -e PGUSER=postgres -e PGDATABASE=judge_load "$DB_CONTAINER" sh /tmp/backup.sh /tmp/judge-backup
docker exec -e PGUSER=postgres "$DB_CONTAINER" sh -ec 'createdb judge_restored; pg_restore --exit-on-error --dbname=judge_restored /tmp/judge-backup/*.dump'
mkdir -p artifacts
python -m ci.verify_restore > artifacts/restore.txt
