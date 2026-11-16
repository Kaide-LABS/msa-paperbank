#!/bin/sh
set -eu

# Cutover step 02 — copy the prod GCS bucket to the self-hosted object store.
#
# DRY-RUN BY DEFAULT (same guard as step 01): prints the exact command and exits 0
# WITHOUT running it unless --confirm is passed AND docs/SIGNOFF.md exists and is
# non-empty. READ-ONLY on the source bucket (an rsync pull); never deletes from or
# writes to prod. Writes only into the self-hosted object-store root. NOT executed
# during the build.
#
# Environment only; no secret embedded:
#   SOURCE_BUCKET      gs:// prod bucket (read-only source)
#   OBJECT_STORE_DIR   self-hosted object-store root the files are copied into

CONFIRM=0
for arg in "$@"; do
    case "$arg" in
        --confirm) CONFIRM=1 ;;
        *) echo "unknown argument: $arg" >&2; exit 2 ;;
    esac
done

SIGNOFF=${SIGNOFF_FILE:-docs/SIGNOFF.md}

: "${SOURCE_BUCKET:?SOURCE_BUCKET is required (gs:// prod bucket, read-only)}"
: "${OBJECT_STORE_DIR:?OBJECT_STORE_DIR is required (self-hosted object-store root)}"

# -r mirrors into the destination; we deliberately DO NOT pass -d so nothing on the
# source is ever considered for deletion. Source is read-only throughout.
COPY_CMD="gsutil -m rsync -r \"$SOURCE_BUCKET\" \"$OBJECT_STORE_DIR\""

is_signed_off() {
    [ -s "$SIGNOFF" ] && grep -qE '^## Status:[[:space:]]+GRANTED[[:space:]]*$' "$SIGNOFF" 2>/dev/null
}

if [ "$CONFIRM" -ne 1 ] || ! is_signed_off; then
    echo "DRY RUN — no prod access performed."
    echo "Would run (read-only copy from prod bucket, prod untouched):"
    echo "  $COPY_CMD"
    if [ "$CONFIRM" -ne 1 ]; then
        echo "Refusing real execution: pass --confirm to proceed."
    fi
    if ! is_signed_off; then
        echo "Refusing real execution: $SIGNOFF is absent or unsigned."
    fi
    exit 0
fi

mkdir -p "$OBJECT_STORE_DIR"
echo "SIGNED-OFF run: copying (read-only) from $SOURCE_BUCKET into $OBJECT_STORE_DIR"
eval "$COPY_CMD"
echo "bucket copy complete: $OBJECT_STORE_DIR"
