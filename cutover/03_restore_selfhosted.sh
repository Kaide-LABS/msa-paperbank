#!/bin/sh
set -eu

# Cutover step 03 — restore the dumped archive into the self-hosted Compose Postgres.
#
# Writes ONLY to the self-hosted stack. It reuses the same host guard as
# scripts/restore.sh so it can never target a Cloud SQL / google host, and refuses a
# prod database name. DRY-RUN BY DEFAULT: prints the command and exits 0 unless
# --confirm is passed (no SIGNOFF marker needed here because it touches no prod — but
# the host/DB guards below make an accidental prod write impossible regardless).
#
# Environment only; no secret embedded:
#   DUMP_FILE        the archive produced by step 01 (in STAGING_DIR)
#   POSTGRES_HOST    self-hosted Postgres host (must NOT be a cloudsql/google host)
#   POSTGRES_USER    self-hosted Postgres user
#   POSTGRES_PASSWORD self-hosted Postgres password
#   RESTORE_DATABASE target self-hosted DB name (must NOT be a prod name)

CONFIRM=0
for arg in "$@"; do
    case "$arg" in
        --confirm) CONFIRM=1 ;;
        *) echo "unknown argument: $arg" >&2; exit 2 ;;
    esac
done

: "${DUMP_FILE:?DUMP_FILE is required (the archive from step 01)}"
: "${POSTGRES_HOST:?POSTGRES_HOST is required}"
: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"
TARGET_DB=${RESTORE_DATABASE:-paperbank}
PROVIDER=${PROVIDER:-local}

# Self-hosted-only guards (same shape as scripts/restore.sh).
case "$PROVIDER" in gcp|gcp-*) echo "refusing restore for GCP provider" >&2; exit 2;; esac
case "$POSTGRES_HOST" in *cloudsql*|*google*|*sqladmin*) echo "refusing Cloud SQL host" >&2; exit 2;; esac
case "$TARGET_DB" in prod|production|gcp_*) echo "restore target must be self-hosted, not prod" >&2; exit 2;; esac

RESTORE_CMD="pg_restore --exit-on-error --no-owner --host=\"$POSTGRES_HOST\" --port=\"${POSTGRES_PORT:-5432}\" --username=\"$POSTGRES_USER\" --dbname=\"$TARGET_DB\" \"$DUMP_FILE\""

if [ "$CONFIRM" -ne 1 ]; then
    echo "DRY RUN — no database write performed."
    echo "Would restore into the self-hosted DB '$TARGET_DB' on '$POSTGRES_HOST':"
    echo "  $RESTORE_CMD"
    echo "Refusing real execution: pass --confirm to proceed."
    exit 0
fi

[ -f "$DUMP_FILE" ] || { echo "dump archive not found: $DUMP_FILE" >&2; exit 2; }
export PGPASSWORD="$POSTGRES_PASSWORD"
echo "restoring into self-hosted DB '$TARGET_DB' on '$POSTGRES_HOST'"
pg_restore --exit-on-error --no-owner \
    --host="$POSTGRES_HOST" --port="${POSTGRES_PORT:-5432}" \
    --username="$POSTGRES_USER" --dbname="$TARGET_DB" "$DUMP_FILE"
echo "restore into $TARGET_DB complete"
