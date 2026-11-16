# Cutover step 07 — Move the WhatsApp webhook (checklist, documentation only)

> **Documentation only. This file executes nothing.** Perform these steps by hand in
> the Meta App dashboard **only after written sign-off**, and only once the new
> self-hosted deploy is verified healthy. GCP prod stays running until the move is
> confirmed, so you can roll back instantly.

The bot receives WhatsApp messages at `POST /webhook` and answers Meta's verification
handshake at `GET /webhook` (challenge echo). Moving the webhook is a single
callback-URL swap in the Meta dashboard — no code change, no data move.

## Pre-conditions
- The new self-hosted deploy is reachable over **public HTTPS** via the reverse proxy
  (see `RUNBOOK.md`), and `GET https://NEW_HOST/healthz` returns `{"ok": true}`.
- The new deploy uses the **same** `WA_VERIFY_TOKEN` and `WA_APP_SECRET` as the GCP
  deploy (env only — never committed), so Meta's verify-token check and the
  `X-Hub-Signature-256` payload signature both continue to match. No token is rotated
  during the move.
- Steps 01–06 are complete and the parity + side-by-side gates passed.

## Move
1. In the Meta App dashboard → **WhatsApp → Configuration → Webhook**, edit the
   **Callback URL** from the GCP deploy URL to `https://NEW_HOST/webhook`.
2. Keep the **Verify token** field unchanged (it must equal the new deploy's
   `WA_VERIFY_TOKEN`). Meta issues a `GET /webhook?hub.mode=subscribe&hub.verify_token=…&hub.challenge=…`;
   the new deploy echoes `hub.challenge` with `200` on a match and `403` otherwise.
3. Confirm the **Webhook fields** subscription (`messages`) is still active.
4. Send a test WhatsApp message and confirm the new deploy logs the inbound and
   replies with a retrieval result.

## Verify
- `GET https://NEW_HOST/healthz` → `200 {"ok": true}`.
- A real test query over WhatsApp returns a paper + signed download link from the new
  deploy.
- The new deploy's logs show `phase=webhook` inbound handling with no signature
  rejections.

## Rollback
- If verification fails, edit the **Callback URL** back to the GCP deploy URL in the
  Meta dashboard. The verify token is unchanged, so the old deploy re-verifies
  immediately and resumes serving. No data is lost because nothing was deleted and GCP
  prod stayed running throughout.
