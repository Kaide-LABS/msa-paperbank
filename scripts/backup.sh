#!/bin/sh
set -eu

: "${POSTGRES_HOST:?POSTGRES_HOST is required}"
: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_DB:?POSTGRES_DB is required}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"
BACKUP_DIR=${BACKUP_DIR:-/backups}
RETENTION_DAYS=${RETENTION_DAYS:-14}
PROVIDER=${PROVIDER:-local}

case "$PROVIDER" in gcp|gcp-*) echo "refusing backup for GCP provider" >&2; exit 2;; esac
case "$POSTGRES_HOST" in *cloudsql*|*google*|*sqladmin*) echo "refusing Cloud SQL host" >&2; exit 2;; esac
case "$RETENTION_DAYS" in ''|*[!0-9]*) echo "RETENTION_DAYS must be numeric" >&2; exit 2;; esac
mkdir -p "$BACKUP_DIR"
stamp=$(date -u +%Y%m%dT%H%M%SZ)
archive="$BACKUP_DIR/paperbank-$stamp.dump"
export PGPASSWORD="$POSTGRES_PASSWORD"
echo "creating $archive"
pg_dump --format=custom --file="$archive" --host="$POSTGRES_HOST" --port="${POSTGRES_PORT:-5432}" --username="$POSTGRES_USER" "$POSTGRES_DB"
find "$BACKUP_DIR" -type f -name 'paperbank-*.dump' -mtime "+$RETENTION_DAYS" -print -delete
echo "backup complete: $archive"
