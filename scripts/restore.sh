#!/bin/sh
set -eu

# Archives live on the mounted /backups volume (BACKUP_DIR); BACKUP_FILE is an
# archive produced by scripts/backup.sh, e.g. /backups/paperbank-<stamp>.dump.
BACKUP_DIR=${BACKUP_DIR:-/backups}
: "${BACKUP_FILE:?BACKUP_FILE is required (e.g. $BACKUP_DIR/paperbank-<stamp>.dump)}"
: "${POSTGRES_HOST:?POSTGRES_HOST is required}"
: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"
TARGET_DB=${RESTORE_DATABASE:-paperbank_restore_drill}
PROVIDER=${PROVIDER:-local}
case "$PROVIDER" in gcp|gcp-*) echo "refusing restore for GCP provider" >&2; exit 2;; esac
case "$POSTGRES_HOST" in *cloudsql*|*google*|*sqladmin*) echo "refusing Cloud SQL host" >&2; exit 2;; esac
case "$TARGET_DB" in paperbank|prod|production|gcp_*) echo "restore target must be non-prod" >&2; exit 2;; esac
[ -f "$BACKUP_FILE" ] || { echo "backup archive not found" >&2; exit 2; }
export PGPASSWORD="$POSTGRES_PASSWORD"
dropdb --if-exists --host="$POSTGRES_HOST" --port="${POSTGRES_PORT:-5432}" --username="$POSTGRES_USER" "$TARGET_DB"
createdb --host="$POSTGRES_HOST" --port="${POSTGRES_PORT:-5432}" --username="$POSTGRES_USER" "$TARGET_DB"
pg_restore --exit-on-error --host="$POSTGRES_HOST" --port="${POSTGRES_PORT:-5432}" --username="$POSTGRES_USER" --dbname="$TARGET_DB" "$BACKUP_FILE"
psql -v ON_ERROR_STOP=1 --host="$POSTGRES_HOST" --port="${POSTGRES_PORT:-5432}" --username="$POSTGRES_USER" --dbname="$TARGET_DB" -c 'SELECT count(*) AS papers FROM papers; SELECT count(*) AS paper_chunks FROM paper_chunks;'
echo "restore drill verified in $TARGET_DB"
