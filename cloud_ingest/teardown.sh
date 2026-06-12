#!/usr/bin/env bash
# Tear down ALL throwaway resources from the cloud ingest test. Safe to re-run.
set -uo pipefail
PROJECT=project-5ef57c09-aaea-42a8-a3f
PROJNUM=1052739697974
REGION=us-central1
BUCKET=paperbank-corpus-test-${PROJNUM}
SQL=pb-throwaway
JOB=cloud-ingest-test
AR=paperbank

# Row-level rollback (use if the throwaway DB is kept/reused instead of dropped):
#   DELETE FROM pending_papers WHERE source='cloud_test';

gcloud run jobs delete ${JOB} --project ${PROJECT} --region ${REGION} --quiet || true
gcloud sql instances delete ${SQL} --project ${PROJECT} --quiet || true     # drops the throwaway DB entirely
gcloud storage rm -r gs://${BUCKET} --project ${PROJECT} || true
gcloud artifacts repositories delete ${AR} --location=${REGION} --project ${PROJECT} --quiet || true
echo "teardown complete"
