#!/usr/bin/env bash
# Cloud Run JOB — corpus ingest TEST batch. Build + deploy + run on a THROWAWAY Cloud SQL.
# NOT the full corpus (that is a separate, gated deploy). All rows tagged source='cloud_test'.
set -euo pipefail

PROJECT=project-5ef57c09-aaea-42a8-a3f
PROJNUM=1052739697974
REGION=us-central1                       # Cloud Run / Cloud SQL / Artifact Registry region
VERTEX_LOC=global                        # Vertex models resolve at 'global' for this project
BUCKET=paperbank-corpus-test-${PROJNUM}  # globally-unique
PREFIX=cloud_test_batch/
AR=paperbank                             # Artifact Registry repo
IMAGE=${REGION}-docker.pkg.dev/${PROJECT}/${AR}/cloud-ingest:test
SQL=pb-throwaway                         # throwaway Cloud SQL instance
DBNAME=paperbank_test
DBUSER=ingest
SA=cloud-ingest-job@${PROJECT}.iam.gserviceaccount.com
JOB=cloud-ingest-test
INSTANCE_CONN=${PROJECT}:${REGION}:${SQL}

# 1) Enable APIs
gcloud services enable run.googleapis.com sqladmin.googleapis.com \
  artifactregistry.googleapis.com cloudbuild.googleapis.com aiplatform.googleapis.com \
  storage.googleapis.com --project ${PROJECT}

# 2) GCS bucket + upload the 40 test files (preserves folder paths)
gcloud storage buckets create gs://${BUCKET} --project ${PROJECT} --location ${REGION} || true
GCS_BUCKET=${BUCKET} python scripts/upload_test_batch.py ${BUCKET} ${PREFIX}

# 3) Artifact Registry repo + build/push the image (Cloud Build — no local Docker push needed)
gcloud artifacts repositories create ${AR} --repository-format=docker \
  --location=${REGION} --project ${PROJECT} || true
gcloud builds submit --tag ${IMAGE} --project ${PROJECT} -f cloud_ingest/Dockerfile .

# 4) Throwaway Cloud SQL (Postgres) + db + user  (db-f1-micro, smallest)
gcloud sql instances create ${SQL} --project ${PROJECT} --region ${REGION} \
  --database-version=POSTGRES_15 --tier=db-f1-micro --storage-size=10 --no-backup
DBPASS=$(python -c "import secrets;print(secrets.token_urlsafe(18))")
gcloud sql databases create ${DBNAME} --instance ${SQL} --project ${PROJECT}
gcloud sql users create ${DBUSER} --instance ${SQL} --password "${DBPASS}" --project ${PROJECT}

# 5) Job service account + IAM (cloudsql.client, aiplatform.user, storage read)
gcloud iam service-accounts create cloud-ingest-job --project ${PROJECT} || true
for ROLE in roles/cloudsql.client roles/aiplatform.user roles/storage.objectViewer; do
  gcloud projects add-iam-policy-binding ${PROJECT} \
    --member="serviceAccount:${SA}" --role="${ROLE}" --condition=None >/dev/null
done

# 6) Deploy the Cloud Run JOB
gcloud run jobs deploy ${JOB} --project ${PROJECT} --region ${REGION} \
  --image ${IMAGE} --service-account ${SA} \
  --set-cloudsql-instances ${INSTANCE_CONN} \
  --memory 2Gi --cpu 2 --max-retries 1 --task-timeout 3600 \
  --set-env-vars "GCP_PROJECT=${PROJECT},GCP_LOCATION=${VERTEX_LOC},GCS_BUCKET=${BUCKET},GCS_PREFIX=${PREFIX},SOURCE_TAG=cloud_test,CONCURRENCY=3,INSTANCE_CONNECTION_NAME=${INSTANCE_CONN},DB_USER=${DBUSER},DB_PASS=${DBPASS},DB_NAME=${DBNAME}"

# 7) COST GATE then EXECUTE once
gcloud run jobs execute ${JOB} --project ${PROJECT} --region ${REGION} --wait

# 8) Verify writes
gcloud sql connect ${SQL} --user=${DBUSER} --project ${PROJECT} --database=${DBNAME} <<'SQL'
SELECT source, count(*) FROM pending_papers GROUP BY source;
SELECT outcome, curation_tier, count(*) FROM pending_papers
  WHERE source='cloud_test' GROUP BY outcome, curation_tier ORDER BY 1,2;
SQL
echo "DBPASS was: ${DBPASS}  (throwaway)"
