# LAUNCH CHECKLIST

- [ ] **Aisha sends a real request, receives PDF in < 30s on 1-bar MTN.**
  Verification: real-device test from a PAU number; record screenshot.

- [ ] **Ibrahim can add a paper from his laptop, queryable in 60s.**
  Verification: `python -m admin.upload pdf ./samples/mth102-har-2022.pdf --year 2022 --semester harmattan`, then `python -m admin.list --year 2022`.

- [ ] **All secrets in Secret Manager. None in repo.**
  Verification: `gcloud secrets list`; `git grep -nE 'WA_ACCESS_TOKEN|DB_PASSWORD|WA_APP_SECRET' -- '*.py' '*.md'` returns nothing.

- [ ] **RUNBOOK.md lets Ibrahim rotate the Meta token unaided.**
  Verification: dry-run by a non-author MSA exec following only RUNBOOK.md §1.

- [ ] **One full month: total GCP bill ≤ $15 post-credits, error rate < 1%.**
  Verification: GCP billing report + `python -m admin.stats --days 30`.