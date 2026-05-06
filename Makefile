PROJECT ?= $(shell gcloud config get-value project)
REGION  ?= africa-south1
SERVICE ?= msa-paperbank
SQL_INSTANCE ?= $(PROJECT):$(REGION):paperbank

.PHONY: deploy migrate logs rollback smoke test drive-import health digest tail drill

deploy:
	gcloud run deploy $(SERVICE) \
	  --source . --region $(REGION) \
	  --service-account $(SERVICE)-sa@$(PROJECT).iam.gserviceaccount.com \
	  --add-cloudsql-instances $(SQL_INSTANCE) \
	  --set-env-vars GCP_PROJECT=$(PROJECT),GCP_LOCATION=global,CLOUD_SQL_INSTANCE=$(SQL_INSTANCE),GCP_LOAD_FROM_SECRETS=1,DB_USER=msa-app,GCS_BUCKET=msa-paperbank-pdfs-$(PROJECT),WA_PHONE_NUMBER_ID=1090588854139402 \
	  --set-secrets DB_PASSWORD=DB_PASSWORD:latest,WA_ACCESS_TOKEN=WA_ACCESS_TOKEN:latest,WA_APP_SECRET=WA_APP_SECRET:latest,WA_VERIFY_TOKEN=WA_VERIFY_TOKEN:latest,ADMIN_BEARER_TOKEN=ADMIN_BEARER_TOKEN:latest \
	  --memory 512Mi --cpu 1 --concurrency 40 --max-instances 2 --min-instances 0

migrate:
	@echo "Apply 001 -> 002 -> 003 -> 004 -> 005 -> 006 in order via Cloud SQL Auth Proxy."
	@echo "Run: gcloud sql connect paperbank --user=$$DB_USER --database=paperbank"
	@echo "Then \i migrations/001_init.sql; \i migrations/002_phase2.sql; ...; \i migrations/006_phase6.sql"

health:
	python -m admin.health

digest:
	python scripts/weekly_digest.py --out weekly_$$(date +%Y-%m-%d).md

tail:
	python -m admin.tail --minutes 60

drill:
	bash scripts/restore_drill.sh

logs:
	gcloud run services logs read $(SERVICE) --region $(REGION) --limit 200

rollback:
	gcloud run services update-traffic $(SERVICE) --region $(REGION) --to-revisions=PREVIOUS=100

smoke:
	./scripts/smoke.sh

test:
	pytest -q

drive-import:
	python scripts/drive_import.py --folder $${DRIVE_FOLDER_ID:?set DRIVE_FOLDER_ID}
