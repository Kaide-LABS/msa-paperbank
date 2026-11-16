#!/bin/sh
set -eu

# Cutover step 01 — read-only export of the prod Cloud SQL database to a local archive.
#
# DRY-RUN BY DEFAULT. This script prints the exact command it would run and exits 0
# WITHOUT running it unless BOTH of these hold:
#   * --confirm is passed, AND
#   * docs/SIGNOFF.md exists and is non-empty (the committed written sign-off marker).
# It is READ-ONLY against prod (an export) and never mutates or deletes anything in
# the GCP production project. It is NOT executed during the migration build — only by an
# operator, on the school's timeline, after written sign-off.
#
# Credentials/identifiers come from the environment only; no secret is embedded here.
#   CLOUDSQL_INSTANCE   fully-qualified Cloud SQL instance connection name
#   CLOUDSQL_DATABASE   source database name (read-only export)
#   EXPORT_BUCKET       gs:// staging bucket the export is written to
#   STAGING_DIR         local mounted dir the export is downloaded into (default ./staging)

CONFIRM=0
for arg in "$@"; do
    case "$arg" in
        --confirm) CONFIRM=1 ;;
        *) echo "unknown argument: $arg" >&2; exit 2 ;;
    esac
done

SIGNOFF=${SIGNOFF_FILE:-docs/SIGNOFF.md}
STAGING_DIR=${STAGING_DIR:-./staging}

: "${CLOUDSQL_INSTANCE:?CLOUDSQL_INSTANCE is required (env only; no secret in-script)}"
: "${CLOUDSQL_DATABASE:?CLOUDSQL_DATABASE is required}"
: "${EXPORT_BUCKET:?EXPORT_BUCKET is required (gs:// staging bucket)}"

# The read-only export command (shown in dry-run, executed only after sign-off).
EXPORT_CMD="gcloud sql export sql \"$CLOUDSQL_INSTANCE\" \"$EXPORT_BUCKET/paperbank-cutover.sql.gz\" --database=\"$CLOUDSQL_DATABASE\" --offload"

is_signed_off() {
    [ -s "$SIGNOFF" ] && grep -qE '^## Status:[[:space:]]+GRANTED[[:space:]]*$' "$SIGNOFF" 2>/dev/null
}

if [ "$CONFIRM" -ne 1 ] || ! is_signed_off; then
    echo "DRY RUN — no prod access performed."
    echo "Would run (read-only export, prod untouched):"
    echo "  $EXPORT_CMD"
    echo "  gsutil cp \"$EXPORT_BUCKET/paperbank-cutover.sql.gz\" \"$STAGING_DIR/\""
    if [ "$CONFIRM" -ne 1 ]; then
        echo "Refusing real execution: pass --confirm to proceed."
    fi
    if ! is_signed_off; then
        echo "Refusing real execution: $SIGNOFF is absent or unsigned."
    fi
    exit 0
fi

mkdir -p "$STAGING_DIR"
echo "SIGNED-OFF run: exporting (read-only) from $CLOUDSQL_INSTANCE"
eval "$EXPORT_CMD"
gsutil cp "$EXPORT_BUCKET/paperbank-cutover.sql.gz" "$STAGING_DIR/"
echo "export complete: $STAGING_DIR/paperbank-cutover.sql.gz"
