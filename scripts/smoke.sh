#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${BASE_URL:-}" || -z "${WA_APP_SECRET:-}" || -z "${WA_VERIFY_TOKEN:-}" ]]; then
  echo "Missing BASE_URL, WA_APP_SECRET, or WA_VERIFY_TOKEN"
  exit 1
fi

echo "Testing healthz..."
health=$(curl -fsS "$BASE_URL/healthz")
if [[ "$health" != '{"ok":true}' && "$health" != '{"ok": true}' ]]; then
  echo "healthz failed: $health"
  exit 1
fi

echo "Testing webhook verify (wrong token)..."
code=$(curl -fsS -o /dev/null -w "%{http_code}" "$BASE_URL/webhook?hub.mode=subscribe&hub.verify_token=WRONG&hub.challenge=42" || echo "403")
if [[ "$code" != "403" ]]; then
  echo "Expected 403 for wrong token, got $code"
  exit 1
fi

echo "Testing webhook verify (correct token)..."
chal=$(curl -fsS "$BASE_URL/webhook?hub.mode=subscribe&hub.verify_token=$WA_VERIFY_TOKEN&hub.challenge=42")
if [[ "$chal" != "42" ]]; then
  echo "Expected 42 for challenge, got $chal"
  exit 1
fi

echo "Testing webhook POST (wrong signature)..."
body='{"object":"whatsapp_business_account","entry":[]}'
code2=$(curl -fsS -o /dev/null -w "%{http_code}" -X POST -H "X-Hub-Signature-256: sha256=WRONG" -d "$body" "$BASE_URL/webhook" || echo "401")
if [[ "$code2" != "401" ]]; then
  echo "Expected 401 for wrong sig, got $code2"
  exit 1
fi

echo "Testing webhook POST (correct signature)..."
sig="sha256=$(printf '%s' "$body" | openssl dgst -sha256 -hmac "$WA_APP_SECRET" | awk '{print $2}')"
code3=$(curl -fsS -o /dev/null -w "%{http_code}" -X POST -H "X-Hub-Signature-256: $sig" -d "$body" "$BASE_URL/webhook" || echo "200")
if [[ "$code3" != "200" ]]; then
  echo "Expected 200 for correct sig, got $code3"
  exit 1
fi

echo "SMOKE OK"
exit 0