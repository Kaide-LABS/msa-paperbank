# Copilot Studio spike

**Question this answers:** can a Copilot Studio agent in Teams call our retrieval endpoint, and hand a student a paper they can actually open?

Nothing here touches the school server, the real database or GCP. `stub_server.py` has the same contract as the real endpoint
(`POST /tool/retrieve` with a bearer token, signed `GET /download`) but returns fake papers. What you learn carries over.

## Setup (about 30 minutes)

1. **Run the stub.** In this folder:
   ```
   pip install fastapi uvicorn
   set SPIKE_TOKEN=<a long random string>
   set PUBLIC_BASE_URL=https://<tunnel-host>      (fill in after step 2, then restart)
   python -m uvicorn stub_server:app --port 8000
   ```
2. **Expose it over public HTTPS.** Copilot Studio calls from Microsoft's cloud, so `localhost` will not work.
   Easiest: Microsoft Dev Tunnels (`winget install Microsoft.devtunnel`, then `devtunnel user login`,
   then `devtunnel host -p 8000 --allow-anonymous`). Cloudflare Tunnel or ngrok work too. Copy the https host.
   Check `https://<host>/healthz` in a browser. Restart the stub with `PUBLIC_BASE_URL` set to that host.
3. **Edit `openapi.yaml`:** set `host:` to the tunnel host (no `https://`).
4. **Create the agent** at copilotstudio.microsoft.com in the school tenant (or a test tenant). Add a tool from a REST API,
   upload `openapi.yaml`, and pick the `RetrievePaper` operation. For authentication choose API key, location Header,
   header name `Authorization`, and enter the value as `Bearer <your SPIKE_TOKEN>`. Do the same for `ProbeInput`.
5. **Agent instructions** (paste as-is): "You help PAU students find past exam papers. When a student asks for a past paper,
   call RetrievePaper with their request. If found, tell them the course, year and semester and give the download link.
   If not found, say so and ask for the course code. Never invent a link."
6. **Publish to Teams:** Channels, Microsoft Teams, then open it in Teams yourself. Admin approval is only needed to
   make it available to other people.

The stub writes every request to `spike_requests.jsonl` (token never logged). That file is the evidence.

## Tests

Run each from Teams and fill in the last column. "Evidence" is a line in `spike_requests.jsonl` or a screenshot.

| # | Test | What to do | Pass if | Result |
|---|------|-----------|---------|--------|
| T1 | Text query, found | "past paper for linear algebra" | agent calls RetrievePaper, replies with course, year, link | |
| T2 | Not found | "astrophysics past paper" | agent says nothing was found, does not invent a link | |
| T3 | Course filter | "MAT201 2022" | request body in the log has `prefer_courses` filled or sensible `query` | |
| T4 | Auth failure | wrong token in the connection, ask again | agent says it cannot reach the service, no crash | |
| T5 | Link opens (real behaviour) | click the link on desktop Teams, then mobile Teams | file opens or downloads as a usable PDF | |
| T6 | Link opens (pdf mode) | restart stub with `SPIKE_DOWNLOAD_MODE=pdf`, repeat T5 | opens as PDF with a filename. If T5 failed and T6 passes, fix `/download` in the app | |
| T7 | Link expiry | wait 16 minutes, click the old link | 403 | |
| T8 | Photo in the chat | attach a photo, say "find the paper for this" | see what `ProbeInput` receives: bytes, a URL, a reference, or nothing | |
| T9 | Pasted screenshot | paste a screenshot instead | same as T8 | |
| T10 | Two photos at once | attach two | does the agent see both? | |
| T11 | Speed | note seconds from send to reply | under about 10 s without the real DB. Real backend will add embedding time | |
| T12 | Who can reach it | ask someone else in the tenant to try | works for a second user, or needs admin approval (note which) | |

## What the results decide

- **T8/T9/T10 all fail:** photo search is not possible through Copilot Studio. The design becomes text-only in Teams, and photos stay a WhatsApp feature.
- **T8 gives a URL or reference but not bytes:** the backend needs a way to fetch the image (a Microsoft Graph call), which is more work.
- **T8 gives base64:** the backend can take the image directly; we add an input to `/tool/retrieve`.
- **T5 fails but T6 passes:** the real app must send `application/pdf` and a filename from `/download`. A small fix.
- **T4 or T12 problems:** an auth or tenant-policy conversation with IT before building more.

## Known gaps (not tested here)

- Large file download through the Teams mobile app on a campus network.
- Throughput with many students at once. The real endpoint's embedding and database time is not in this stub.
- Whether the school's tenant allows custom REST tools in Copilot Studio at all (a policy setting). T12 and step 4 reveal this early.

When done, delete the tunnel and stop the stub. Keep `spike_requests.jsonl` and your screenshots, then send them to me.
