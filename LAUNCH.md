# LAUNCH CHECKLIST

This checklist must be executed and verified before the public launch of `msa-paperbank`.

## 1. Security & Identity
- [ ] **All secrets in Secret Manager. None in repo.**
  Verify: `gcloud secrets list && git grep -nE 'WA_ACCESS_TOKEN|DB_PASSWORD|WA_APP_SECRET' -- '*.py' '*.md' | grep -v EXAMPLE`
- [ ] **Admin Bearer Token configured.**
  Verify: `gcloud secrets versions access latest --secret=ADMIN_BEARER_TOKEN` returns a non-empty string.

## 2. Infrastructure & Health
- [ ] **Health probe green.**
  Verify: `make health`
- [ ] **Cloud Run scales to zero.**
  Verify: `gcloud run services describe msa-paperbank --format='value(spec.template.spec.containers[0].resources.limits.cpu)'` is configured and `min-instances` is 0.
- [ ] **Backup restore drill executed within the last 90 days.**
  Verify: `scripts/restore_drill.sh` produced a successful run, log saved.

## 3. Product & Quality
- [ ] **End-to-end retrieval works on real device.**
  Verify: Send "MTH102 harmattan 2022" from a real PAU number; receive correct PDF within 30s.
- [ ] **Cost cap configured and tested.**
  Verify: Temporarily set `DAILY_COST_USD_CAP=0.0001`, send a request, see "daily limit" reply; reset to `0.50`.
- [ ] **Personalization working.**
  Verify: Send 5 requests for MTH102, then send "MTH" and see if MTH102 is prioritized/suggested.
- [ ] **Opt-out working.**
  Verify: Send "STOP TRACKING", see confirmation, verify `interaction_count` is 0 in DB.

## 4. Operations
- [ ] **Weekly digest rehearsed.**
  Verify: `make digest` produces a valid Markdown file.
- [ ] **Successor hand-off.**
  Verify: Ibrahim has `Owner` role on GCP project and `Admin` on Meta Business Manager.

---
**Sadaqah Jariyah.** May this benefit the students of PAU.
