#!/bin/bash
set -euo pipefail

# This script is for an interactive backup restore drill.
# It should NOT be run in CI.

echo "WARNING: this creates a temporary Cloud SQL instance and restores the latest backup into it."
echo "The production instance is NOT touched."
read -p "Continue? [yes/N]: " confirm

if [[ "$confirm" != "yes" ]]; then
    echo "Aborted."
    exit 0
fi

INSTANCE="paperbank"
REGION="${REGION:?set REGION}"
PROJECT="${PROJECT:?set PROJECT}"

echo "Fetching latest successful backup..."
BACKUP_ID=$(gcloud sql backups list --instance $INSTANCE --filter='status=SUCCESSFUL' --sort-by=~window_start_time --limit=1 --format='value(id)')

if [[ -z "$BACKUP_ID" ]]; then
    echo "No successful backups found."
    exit 1
fi

DRILL_INSTANCE="paperbank-drill-$(date +%Y%m%d-%H%M)"
echo "Creating drill instance: $DRILL_INSTANCE (this takes a few minutes)..."
gcloud sql instances create $DRILL_INSTANCE \
    --database-version=POSTGRES_16 \
    --tier=db-f1-micro \
    --region=$REGION \
    --quiet

echo "Restoring backup $BACKUP_ID to $DRILL_INSTANCE..."
gcloud sql backups restore $BACKUP_ID \
    --restore-instance=$DRILL_INSTANCE \
    --backup-instance=$INSTANCE \
    --quiet

echo "Drill instance ready. Running smoke tests..."
# In a real scenario, you'd use Cloud SQL Proxy here. 
# For the sake of the script, we'll assume the environment has access.
# Since we can't easily run the proxy and psql here without more setup, 
# we'll use gcloud sql connect (which is interactive).

echo "I will now open a connection to the drill instance."
echo "Please run the following query manually to verify data:"
echo "SELECT count(*) FROM papers; SELECT count(*) FROM courses; SELECT count(*) FROM request_log;"
echo "After verifying, exit the psql shell."

gcloud sql connect $DRILL_INSTANCE --user=postgres

read -p "Drill complete. Delete temp instance $DRILL_INSTANCE? [yes/N]: " cleanup

if [[ "$cleanup" == "yes" ]]; then
    gcloud sql instances delete $DRILL_INSTANCE --quiet
    echo "Temp instance deleted."
else
    echo "LEFT INTACT — remember to delete manually with: gcloud sql instances delete $DRILL_INSTANCE --quiet"
fi
