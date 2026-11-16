# Failures and fixes

What went wrong in past runs and what resolved it. One fact per line.

- Run stopped: Build cancelled at approval. _(run 1535cf46, 2026-11-11)_
- Unconfirmed research claim (do not rely on it): GPT-6 (Astra/Sol/Luna) and GPT-5.6/5.5/5.4 reasoning models exist with reasoning_effort/mode params, and Global Standard pricing figures (e.g. GPT-6 Astra $10/$50, GPT-5 $1.25/$10). _(run 1535cf46, 2026-11-11)_
- Run stopped: One AI tool's hand-over note to the next could not be read, so the build was stopped rather than carry on from a possibly wrong state. _(run ef877dec, 2026-11-11)_
- Phase 1 did not complete: ✖ Too big: expected string to have <=4000 characters → at work_done _(run ef877dec, 2026-11-11)_
- Unconfirmed research claim (do not rely on it): Meta WhatsApp Cloud API current Graph API version is v27.0 and /messages remains the send endpoint; webhook signature/handshake mechanics _(run ef877dec, 2026-11-11)_
- Unconfirmed research claim (do not rely on it): Source text contained an instruction aimed at an AI (remote-exec); it was removed and nothing from it was used _(run ef877dec, 2026-11-11)_
- Research item local-cpu-embedder-768 failed: Required field "key_findings" is missing. _(run ef877dec, 2026-11-11)_
- Run stopped: The build stopped before it was finished. _(run ef877dec, 2026-11-15)_
- Phase 4 did not complete: claude-code: The AI provider stopped with an error (it exited with code 1). _(run ef877dec, 2026-11-15)_
- Run stopped: The finished project did not pass the final check. _(run ef877dec, 2026-11-16)_
- Final check found a requirement NOT met: The existing pytest suite passes unchanged after Phase 1 (tests minimally re-pointed at new seams are allowed; no behavioural assertion changed). _(run ef877dec, 2026-11-16)_
- Final check found a requirement NOT met: Ports exist for object store, embedder, secrets, and DB engine, selectable by a provider setting, with the existing GCP implementations behind them. _(run ef877dec, 2026-11-16)_
- Final check found a requirement NOT met: The gcs_* rename is applied via a reversible migration using SQLAlchemy synonyms, and the pre-existing env variable names still resolve. _(run ef877dec, 2026-11-16)_
- Final check found a requirement NOT met: No plaintext DB password, Cloud SQL connection string, or hardcoded GCP project id remains in apply_migrations.py, scripts, or the Dockerfile. _(run ef877dec, 2026-11-16)_
- Final check found a requirement NOT met: A re-embed job repopulates chunk and title embeddings, and a recorded parity report compares old vs new top-k results on a fixed query set. _(run ef877dec, 2026-11-16)_
- Final check found a requirement NOT met: docker compose up starts bot + Postgres (pgvector, pg_trgm) + optional MinIO, and each service reports healthy via its health check. _(run ef877dec, 2026-11-16)_
- Final check found a requirement NOT met: Phase 6 migration/cutover/teardown scripts exist but are not executed, and GCP production remains running and reversible. (the check could not exercise this criterion) _(run ef877dec, 2026-11-16)_
