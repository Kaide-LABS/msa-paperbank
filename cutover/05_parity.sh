#!/bin/sh
set -eu

# Cutover step 05 — before/after top-k parity over the fixed query set.
#
# Thin wrapper over the already-shipped parity harness (app/parity.py / run_parity).
# It compares the pre-re-embed (restored Vertex) top-k against the post-re-embed
# (local CPU) top-k on the fixed query set in data/parity_queries.json and prints the
# per-query Jaccard@k + rank correlation plus the means. The pass gate is the
# threshold recorded in docs/parity_report.md (mean Jaccard@10 >= 0.70, mean rank
# correlation >= 0.60). Read-only against the DB; no DDL; no network beyond the local
# model. DRY-RUN BY DEFAULT.
#
# Environment only; no secret embedded:
#   PARITY_OLD_SNAPSHOT  JSON mapping each query to its old (Vertex-era) top-k vector
#   PARITY_QUERIES       query set file (default data/parity_queries.json)
#   PARITY_K             top-k (default 10)

CONFIRM=0
for arg in "$@"; do
    case "$arg" in
        --confirm) CONFIRM=1 ;;
        *) echo "unknown argument: $arg" >&2; exit 2 ;;
    esac
done

PROVIDER=${PROVIDER:-local}
QUERIES=${PARITY_QUERIES:-data/parity_queries.json}
PARITY_K=${PARITY_K:-10}
case "$PROVIDER" in gcp|gcp-*) echo "refusing parity run for GCP provider" >&2; exit 2;; esac
: "${PARITY_OLD_SNAPSHOT:?PARITY_OLD_SNAPSHOT is required (old top-k vector snapshot)}"

PARITY_CMD="python -m app.parity --queries \"$QUERIES\" --old-snapshot \"$PARITY_OLD_SNAPSHOT\" -k $PARITY_K"

if [ "$CONFIRM" -ne 1 ]; then
    echo "DRY RUN — no parity run performed."
    echo "Would compute top-k parity (gate: docs/parity_report.md thresholds):"
    echo "  $PARITY_CMD"
    echo "Refusing real execution: pass --confirm to proceed."
    exit 0
fi

echo "running parity over $QUERIES"
eval "$PARITY_CMD"
