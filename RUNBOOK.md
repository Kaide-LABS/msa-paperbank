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

## 4. Silent Bot Triage
If the bot stops replying:
1. Run `make health`. If any sub-check is `FAIL`, that is your symptom.
2. Check `make tail --minutes 30` to see if incoming messages are being received and what the outcome is.
3. Check Cloud Run logs for 500s or timeouts.

## 5. Database Restore (Drill & Emergency)
We perform a quarterly restore drill to ensure our backups are valid.
- **Drill**: Run `make drill` (or `bash scripts/restore_drill.sh`). This creates a *new* instance, restores the latest backup, and prompts you to verify data. It does NOT touch production.
- **Emergency**: To restore production in-place (destructive!), use the GCP Console: Cloud SQL -> paperbank -> Backups -> Restore.

## 6. Curation queue
After every Drive import, run `python -m admin.curate` to walk the queue. The bot does not retrieve a paper until you approve it.

## 10. Privacy / opt-out
Any user can wipe their record by sending STOP TRACKING. To reset a single user's profile without opting them out: `python -m admin.users reset <PHONE> --yes`. To export a user's data on request: `python -m admin.users export <PHONE> --out user.json`.

## 11. Cost Dashboards
- Run `make digest` weekly.
- Check the `Spend` section. If it trends > $2/day for 3+ days, investigate for abuse or raise the `DAILY_COST_USD_CAP` deliberately in Secret Manager.
- The `admin stats` command also provides a live snapshot of usage.
