# Cutover sign-off record

> **UNSIGNED PLACEHOLDER.** This file is the written sign-off marker that the
> prod-touching cutover scripts (`cutover/01_dump_cloudsql.sh`,
> `cutover/02_copy_bucket.sh`) check for. While it remains unsigned, those scripts stay
> in dry-run and refuse to touch GCP production. It contains **no secret** and must
> never carry one.

The scripts treat this file as authorising a real run only when it contains a status
line that begins with `## Status:` followed by the single word `GRANTED`. While the
status line below reads anything else, every prod-touching cutover step is inert
(dry-run) and reaches no GCP service.

## Status: PENDING

## How to authorise
To authorise the operational cutover, the owner edits the status line above so it reads
`## Status:` followed by `GRANTED` (nothing else on that line), fills in the
attestation below, and commits:

- Authorised-by: &lt;owner name / role&gt;
- Date: &lt;YYYY-MM-DD&gt;
- Scope: run cutover steps 01–08 against production once, then move the WhatsApp webhook.

## What sign-off authorises
- Executing the cutover runbook (`CUTOVER.md`) steps 01–08 against production **once**.
- Moving the WhatsApp webhook to the self-hosted deploy (`cutover/07_webhook_move.md`).

## What sign-off does NOT authorise
- Deleting or modifying the GCP **project/infrastructure** (prod Cloud SQL, bucket,
  Secret Manager). GCP production stays running and reversible until a separate,
  explicit teardown decision by the owner.
