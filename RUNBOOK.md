# RUNBOOK

## 1. Rotate the Meta access token
- Go to Meta Business Manager -> System Users.
- Generate a new token with WhatsApp permissions.
- Save to Secret Manager: `gcloud secrets versions add WA_ACCESS_TOKEN --data-file=-`
- Run `make deploy` to restart Cloud Run.

## 2. Add a past paper
### PDF Upload
`python -m admin.upload pdf ./path/to/paper.pdf --year 2024 --semester rain`

### Image Upload
`python -m admin.upload images ./path/to/page1.jpg ./path/to/page2.jpg --year 2024 --semester rain`

## 3. Retire a paper
If a lecturer points out a paper shouldn't be shared (e.g., active use risk):
`python -m admin.retire 123 --reason "Lecturer requested removal" --yes`

## 4. The bot is silent — what to check
1. Run `make smoke`.
2. Check Meta webhook health in the Meta App Dashboard.
3. Check Cloud Run logs: `make logs`.
4. Check Cloud SQL is reachable.
5. Check Vertex AI quotas.
6. Check `python -m admin.courses list` — if the course the user asked about is missing or `is_active=FALSE`, that's the cause.
7. If still silent, escalate.

## 5. Restore from backup
- Cloud SQL automated backups are enabled by default.
- Restore using `gcloud sql backups restore <BACKUP_ID> --restore-instance=paperbank`.
- Verify database state.
- Re-run missing migrations if needed via Cloud SQL Auth Proxy.

If `admin stats --days 7` shows tokens > 1.4M, something is wrong — open an issue.

## 6. Curation queue
After every Drive import, run `python -m admin.curate` to walk the queue. The bot does not retrieve a paper until you approve it.

## 7. Mass-retire a course
`python -m admin.retire --course CSC305 --reason "syllabus rotated" --yes`