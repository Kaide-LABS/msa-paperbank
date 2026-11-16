#!/bin/sh
set -eu

# Cutover step 04 — re-embed the restored rows with the local CPU embedder.
#
# Thin wrapper over the already-shipped `python -m app.reembed` (Phase 4's
# reembed_all): replaces the restored Vertex vectors with local 768-dim vectors in the
# unchanged Vector(768) column. No schema change; no DDL on the default path; no
# network beyond the local model. Writes only to the self-hosted DB (app.reembed
# itself raises for provider=gcp). DRY-RUN BY DEFAULT.
#
# Environment only; no secret embedded. PROVIDER must not be gcp.

CONFIRM=0
for arg in "$@"; do
    case "$arg" in
        --confirm) CONFIRM=1 ;;
        *) echo "unknown argument: $arg" >&2; exit 2 ;;
    esac
done

PROVIDER=${PROVIDER:-local}
BATCH_SIZE=${REEMBED_BATCH_SIZE:-32}
case "$PROVIDER" in gcp|gcp-*) echo "refusing re-embed for GCP provider" >&2; exit 2;; esac

REEMBED_CMD="python -m app.reembed --batch-size $BATCH_SIZE"

if [ "$CONFIRM" -ne 1 ]; then
    echo "DRY RUN — no re-embed performed."
    echo "Would run against the self-hosted DB (local CPU embedder, no schema change):"
    echo "  $REEMBED_CMD"
    echo "Refusing real execution: pass --confirm to proceed."
    exit 0
fi

echo "re-embedding self-hosted rows with the local CPU embedder"
exec $REEMBED_CMD
