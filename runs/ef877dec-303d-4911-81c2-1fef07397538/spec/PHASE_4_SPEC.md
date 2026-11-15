# Phase 4 — Local CPU embedder (768-dim) behind the `Embedder` port, re-embed job, before/after top-k parity harness with a recorded report

## Goal
Remove the backend's last model-API dependency: add a **local CPU embedding model producing 768-dimension vectors** behind the existing `app.ports.Embedder`, selected by `settings.provider`, so the `Vector(768)` schema and the HNSW / `pg_trgm` indexes are retained **unchanged**. Reroute the two live embedder call sites (`app/retrieval.py` query path, `app/intake.py` chunk-embedding path) through the factory so the active embedder is the one the provider selects. Add an operator **re-embed job** that repopulates `paper_chunks.embedding` (and `pending_paper_chunks.embedding`) from each row's `.text` without touching the schema, and a **before/after top-k parity harness** over a fixed query set that computes overlap/rank-correlation and writes a **recorded parity report** with a proposed pass threshold. No behaviour regression on the live WhatsApp path; GCP production (`ummah`) is never touched, never re-embedded, and stays reversible. Satisfies AC 8, 9.

## Scope
In: a new `app/providers/local/embedder.py` (`LocalCpuEmbedder`, `sentence-transformers` `all-mpnet-base-v2`-class model, native 768-dim, CPU, lazily loaded — never at import, never a network fetch at import) implementing the full `Embedder` port (`embed_one`/`embed_query`/`embed_documents`/`dim`); the factory (`app/providers/__init__.py`) extended so `get_embedder` returns the local embedder for `settings.provider` in `"local"`/`"minio"` and `"gcp"` unchanged; `app/config.py` fields for the local model (name/path, device, normalize, batch size) with `embedding_dim` staying `768`; rerouting `app/retrieval.py` and `app/intake.py` off the direct `app.embeddings` import onto the active embedder via the factory / `app.state`; a re-embed job (`app/reembed.py`) over `paper_chunks` and `pending_paper_chunks`; a parity harness (`app/parity.py`) plus a newly-authored fixed query set and a recorded report; the `sentence-transformers` runtime dependency added to `requirements.txt`; unit tests (network-free, fake/injected encoder) and a short doc. Out: the Dockerfile/Compose/health/backup/RUNBOOK/reverse-proxy stack (Phase 5); any cutover tooling, data migration, GCP teardown, or modification of GCP prod (Phase 6); any Azure work (never); removing the GCP embedder or its imports (Phase 6 final, sign-off-gated). No new behaviour on the WhatsApp send path; the GCP adapters stay the default (`provider="gcp"`); the schema (`Vector(768)`, HNSW, `pg_trgm`) is unchanged.

Plumbing rule used throughout: the new embedder is added **behind the existing `Embedder` port** and selected by `settings.provider`; the GCP embedder is retained and selected only under `provider=="gcp"`. The model is loaded lazily (at FastAPI `lifespan` or first use), never at import; no unit test downloads a model or opens a network client — the encoder is injectable and tests pass a deterministic fake. The re-embed job and parity harness are **operator tools**: they are scripted and tested but never executed against GCP prod.

## Part A (first agent)

### Files
- `app/providers/local/embedder.py` (new) — `LocalCpuEmbedder` implementing the `Embedder` port over a `sentence-transformers` model (`all-mpnet-base-v2` class, native 768-dim, CPU). Constructor accepts an **injectable encoder** (a loaded model object) so tests inject a fake; `from_settings(settings)` builds the real `SentenceTransformer(settings.embedding_model_name, device=settings.embedding_device)` **lazily on first encode**, never at import and never at construction. `embed_one`/`embed_query`/`embed_documents` all encode with L2 normalization (cosine-ready) and return `list[float]`; `embed_documents` batches at `settings.embedding_batch_size`. Each result is length-checked against `settings.embedding_dim` and raises `EmbeddingError` on a mismatch (mirroring `app.embeddings`). `dim` returns `settings.embedding_dim` (768).
- `app/providers/__init__.py` (edit) — `get_embedder` returns `LocalCpuEmbedder.from_settings(settings)` when `settings.provider` is `"local"`/`"minio"`; `"gcp"` unchanged.
- `app/config.py` (edit) — add `embedding_model_name: str = "sentence-transformers/all-mpnet-base-v2"`, `embedding_model_path: str | None = None` (an optional pre-downloaded local path, preferred over the hub name when set), `embedding_device: str = "cpu"`, `embedding_normalize: bool = True`, `embedding_batch_size: int = 32`. `embedding_dim` stays `768`; `model_embedding` (the Vertex id) is untouched. No secret and no network at import.
- `app/main.py` (edit) — build the active embedder once at `lifespan` via `get_embedder(settings)` and stash it on `request.app.state.embedder`, mirroring `app.state.store`; dispose nothing (CPU model). The GCP default path still works (its `from_settings` is lazy).
- `app/retrieval.py`, `app/intake.py` (edit) — reroute the two live embedder call sites off the direct `from app import embeddings` / `from app.embeddings import embed_many` onto the active embedder: in the request path use `request.app.state.embedder` threaded through (or `get_embedder(settings)` cached for non-request callers); `app/retrieval.py:81` (`embed_query`) and `app/intake.py:208` (`embed_many` → `embed_documents`). Behaviour is identical under `provider=="gcp"` (the GCP embedder delegates to `app.embeddings`); the only change is the seam. `requirements.txt` gains `sentence-transformers`.
- `tests/test_local_embedder.py` (new).

### Interfaces and behaviour
- `LocalCpuEmbedder` — the real model is `all-mpnet-base-v2` (native 768-dim, symmetric: `embed_query` and `embed_documents` use the same encoding, so no `RETRIEVAL_QUERY`/`RETRIEVAL_DOCUMENT` task-type split is needed — the model has none). Vectors are L2-normalized so `cosine_distance` ordering is preserved. The encoder loads lazily and only once; importing the module pulls in no model weights and makes no network call. A dimension mismatch (defensive) raises `EmbeddingError`, matching the GCP embedder's contract so `tests/test_ports_integration.py`'s wrong-dim expectation holds uniformly.
- `get_embedder` — `isinstance(get_embedder(local_settings), Embedder)` holds; the factory never loads the model at selection time (only `from_settings` wiring, which is itself lazy). `"gcp"` returns `GcpEmbedder` exactly as today.
- Rerouting — after the edit, no business-logic module imports `app.embeddings` directly for the live query/intake paths; they obtain the embedder from `app.state`/the factory. The `Vector(768)` columns, the HNSW `vector_cosine_ops` index, and `pg_trgm` are **unchanged** — the embedder swap is values-only.

### Tests (`tests/test_local_embedder.py`)
- `isinstance(LocalCpuEmbedder(fake_encoder), Embedder)` holds (runtime-checkable Protocol).
- With an injected fake encoder returning deterministic 768-dim vectors, `embed_one`/`embed_query`/`embed_documents` return `list[float]` of length 768; `embed_documents` preserves input order and batches; `dim == 768`.
- A wrong-dimension fake encoder makes `embed_one` raise `EmbeddingError` (AC 8 guard; mirrors `test_ports_integration`).
- Importing `app.providers.local.embedder` triggers **no** model download and **no** network call (assert the real `SentenceTransformer` is not constructed at import — patch/spy the loader). The real-model smoke test (if any) is marked as an opt-in integration test skipped by default so the unit run stays network-free (AC 2).

## Part B (second agent)

### Files
- `app/reembed.py` (new) — `reembed_all(session, embedder, *, batch_size=…, tables=("paper_chunks","pending_paper_chunks"))`: iterates each table's rows in id-ordered batches, re-encodes `.text` via `embedder.embed_documents`, and `UPDATE`s the `embedding` column in place. Idempotent and resumable (re-running re-embeds the same rows to the same vectors); **no schema change** — it writes values into the existing `Vector(768)` columns. Offers an optional drop-HNSW-index → bulk-update → recreate-index fast path (guarded by a flag; default off) so a large re-embed does not thrash the index, recreating the exact `hnsw (embedding vector_cosine_ops)` definition from `migrations/002`. A `__main__` entry builds the embedder via `get_embedder(settings)` and a session via the engine provider. It must **not** run against GCP prod.
- `app/parity.py` (new) — `jaccard_at_k(old_ids, new_ids, k)` and `rank_correlation(old_ranks, new_ranks)` (Spearman or Kendall-τ over the intersection), plus `run_parity(session, embedder_old_snapshot, embedder_new, queries, *, k)` that, for each query in a fixed set, records the top-k `paper_id` list before (baseline snapshot) and after re-embedding and computes per-query Jaccard@k + rank-correlation and the set means. No relevance labels are used (none exist). Writes a recorded report.
- `data/parity_queries.json` (or `tests/fixtures/parity_queries.json`) (new) — a **newly-authored** fixed query set: a representative sample (≈15–25) of real past-paper queries (course-code and natural-language forms), since none was provided.
- `docs/parity_report.md` (new) — the recorded before/after parity report: the query set, per-query and mean Jaccard@k and rank-correlation, the environment it was run in, and the **proposed pass threshold** (e.g. mean Jaccard@10 ≥ 0.7 and mean rank-correlation ≥ 0.6) with a one-line rationale. If a populated corpus is unavailable in this environment, the report documents the methodology and a run on seeded/sample data and states that the authoritative run is operator-executed post-migration (never against prod).
- `docs/local_embedder.md` (new) — documents the local model (name, 768-dim, CPU, where to pre-download it for an offline server), the `Embedder` seam, the re-embed job (how to run it, the index fast-path, that it never runs against prod), and the parity harness + threshold. It must not instruct running any fetched code and must not edit the PRD.
- `tests/test_reembed.py`, `tests/test_parity.py` (new).

### Interfaces and behaviour
- `reembed_all` — given a fake embedder and an in-memory/sqlite session seeded with chunk rows, it updates every row's `embedding` and leaves `text`, ids, and all other columns untouched; re-running is a no-op on identical input. It never issues DDL except the optional, flag-gated index drop/recreate (and that recreates the identical index). It reads the embedder via the port, so it works under `local` without any Vertex import.
- `jaccard_at_k` / `rank_correlation` — pure functions over id lists; `jaccard_at_k` returns `|A∩B| / |A∪B|` on the top-k sets; `rank_correlation` returns a coefficient in `[-1, 1]`. Deterministic, no DB, no network.
- `run_parity` — produces a structured result (per-query metrics + means) that `docs/parity_report.md` is rendered from; it reads top-k via the same `cosine_distance` ordering the live retrieval uses, so the parity reflects real retrieval behaviour.
- The schema is untouched end-to-end: `Vector(768)`, the HNSW index, and `pg_trgm` are exactly as migrations `001`–`007` leave them (AC 8).

### Tests (`tests/test_reembed.py`, `tests/test_parity.py`)
- `reembed_all` with a fake embedder updates seeded `paper_chunks`/`pending_paper_chunks` rows' `embedding` to the fake's vectors, leaves other columns unchanged, and is idempotent on a second run; no network (AC 2).
- `jaccard_at_k` returns 1.0 for identical top-k, 0.0 for disjoint, and the correct fraction for a partial overlap; `rank_correlation` returns 1.0 for identical ordering and ~−1.0 for a reversed ordering.
- `run_parity` over a tiny seeded corpus with two fake embedders yields per-query metrics and means in range; the fixed query set file loads and is non-empty.
- No test downloads a model, opens a network client, or touches GCP.

## Acceptance-criteria mapping
- **AC 8 — local embedder produces 768-dim vectors; `Vector(768)` + HNSW retained unchanged:** `LocalCpuEmbedder` encodes to native 768-dim and length-checks against `settings.embedding_dim`; the factory selects it under `local`/`minio`; no migration changes the `Vector(768)` columns or the `hnsw (embedding vector_cosine_ops)` / `pg_trgm` indexes. Check: `tests/test_local_embedder.py` asserts 768-length output and `dim==768`; the wrong-dim fake raises `EmbeddingError`.
- **AC 9 — re-embed job repopulates chunk and title embeddings; recorded parity report compares old vs new top-k on a fixed query set:** `app/reembed.py` re-encodes every `paper_chunks`/`pending_paper_chunks` row's `.text` in place; `app/parity.py` + the fixed query set + `docs/parity_report.md` record the before/after top-k comparison with a proposed threshold. Check: `tests/test_reembed.py` asserts the in-place update + idempotency; `tests/test_parity.py` asserts the metric functions and a seeded end-to-end run; `docs/parity_report.md` exists and states the threshold.
- **AC 2 (carried) — no network in unit tests:** the embedder's encoder is injectable and the real model load is lazy and opt-in-only; re-embed/parity tests use fakes and sqlite. Check: suite runs with no outbound network and no model download.
- **AC 1 (carried) — existing pytest passes:** the GCP embedder stays the default and unchanged; the two rerouted call sites behave identically under `provider=="gcp"`; the schema is untouched. Check: `pytest` passes in the project's Python 3.12 environment.

## Documentation sources
- `sentence-transformers` — `SentenceTransformer`, `encode`, normalization: https://www.sbert.net/
- `all-mpnet-base-v2` model card (768-dim, CPU): https://huggingface.co/sentence-transformers/all-mpnet-base-v2
- ONNX Runtime (optional CPU inference path): https://onnxruntime.ai/docs/
- `pgvector` — `Vector`, `cosine_distance`, HNSW: https://github.com/pgvector/pgvector
- SciPy — Spearman / Kendall-τ rank correlation: https://docs.scipy.org/doc/scipy/reference/stats.html
- Hugging Face Transformers — offline/local model caching (`HF_HOME`, local path): https://huggingface.co/docs/transformers/installation#offline-mode

## Out of scope for this phase
- Dockerfile build-out / Docker Compose / health checks / logging / nightly backup / README / RUNBOOK / reverse-proxy guidance (Phase 5).
- Any cutover tooling, GCP teardown, data migration, or modification of GCP prod (`ummah`); any Azure work. The re-embed job is never executed against prod this phase.
- Removing the GCP embedder or its `app.embeddings` / `google-genai` imports (that is the Phase 6 final, sign-off-gated delete).
- Switching the live WhatsApp send path's behaviour; only the embedder values and the query/intake seam change.
- Topic-level search and question-index work (separate later run).

## Spec assumptions

Gaps found while writing this spec were resolved as follows (nobody was asked):

- **The local model is `sentence-transformers/all-mpnet-base-v2`** (native 768-dim, CPU, symmetric encoding), chosen to maximise top-k parity with the retained `Vector(768)`/HNSW schema; ONNX Runtime is an optional alternative inference path, not required. Exact model may be revisited in the parity report if parity is below threshold.
- **"Title embeddings" are chunk rows**, not a separate column: the schema stores question/title text as `paper_chunks` rows (`chunk_kind`), each with one `Vector(768)` `embedding`; the re-embed job repopulating `paper_chunks`/`pending_paper_chunks` covers both.
- **The parity "old vs new" is a baseline snapshot vs a post-re-embed snapshot on a local corpus**, since prod is never touched and stored Vertex vectors are not re-derivable offline; the authoritative prod-corpus parity run is an operator step performed after the data migration (Phase 6), recorded then. This phase delivers the harness, the fixed query set, and a recorded report on available/seeded data.
- **The parity pass threshold is proposed in the report** (the PRD specifies the check, not a number): mean Jaccard@10 ≥ 0.7 and mean rank-correlation ≥ 0.6, adjustable with rationale.
- **The embedder call sites are rerouted through the port this phase** (the reroute Phase 1 deferred), because Phase 4 is the phase that actually swaps the embedder; under `provider=="gcp"` behaviour is identical.
- The authoritative tree is the root-level codebase; the nested `msa-paperbank/` mirror and the root `PHASE_*`/`MASTER_PRD.md` files are not this run's artifacts and are not edited.

## Implications

Second-order consequences found by an independent review of this spec. This section only adds to the spec; the locked PRD is unchanged.

### Additional acceptance criteria

E1. The real embedding model must **never load at import time and must make no network call during the unit-test run**: the encoder is injectable, `from_settings` loads lazily on first encode, and any real-model test is an opt-in integration test skipped by default. A test must assert that importing the adapter does not construct a `SentenceTransformer`. _(AC 2 / correctness)_

E2. The embedder swap is **values-only**: no migration added this phase may alter the `Vector(768)` columns, the HNSW `vector_cosine_ops` index, or `pg_trgm`. The re-embed job's optional index fast-path must recreate the **identical** index definition. A test or review must confirm no DDL changes the schema. _(AC 8 / correctness)_

E3. The re-embed job must be **idempotent and prod-safe**: re-running yields identical vectors, it updates only the `embedding` column, and it has no code path that connects to or writes GCP prod. It is an operator tool, not run in CI against any real corpus. _(correctness/safety)_

E4. The local embedder's output must be **cosine-ready** (L2-normalized) so the existing `cosine_distance` retrieval ordering is valid; a non-normalized model would silently degrade top-k. The adapter normalizes and a test asserts unit-norm (within tolerance) on the injected-vector path. _(correctness)_

### Carried-over Phase 3 cleanup (fix opportunistically while touching the config/providers and tests)

- **Missing source-hygiene grep test (test-coverage — add):** Phase 3's spec (`tests/test_secrets_engine_auth.py`, line 56; implications S3) required a source-hygiene test that greps the repo for the known plaintext DB password, the Cloud SQL instance string, and the hardcoded GCP project-id literal and asserts **zero** matches — the mechanical guard for AC 7. It was not written; `tests/test_secrets_engine_auth.py` covers only env/file secrets, engine laziness, and tool auth. AC 7 therefore has no automated regression guard. Add the grep test (over tracked sources; note that `apply_migrations.py` and `infra_bootstrap.sh` are git-ignored so they are clean-by-exclusion, but `.env.example` placeholders and `tests/conftest.py` dummies must be allow-listed). _(carried AC-7 verification gap flagged by the Phase 3 reviewer.)_
- **Optional MinIO fake-client coverage (test-coverage — optional):** Phase 3's `MinioObjectStore` is a thin SDK-gated adapter never exercised by a fake-S3-client test (the spec allowed this as "optional"). If the `minio` surface is touched, add a fake-client round-trip test (`put`/`get`/`exists`/`delete` + `signed_url` verifies) so the adapter has a regression guard without a live MinIO. _(coverage, non-blocking.)_

### Noted, no action

- AC 1 ("full suite green") remains verifiable only in the project's real **Python 3.12** environment: the sandbox runs Python 3.14 where `conftest.py`'s partial `reportlab` mock makes `reportlab.lib` a non-package, so any test transitively importing `app.pdfgen` (via `app.intake`/`app.pipeline`) fails at collection (≈10 modules). The Phase 3 touched-surface tests (29) pass here; confirm the full suite green under 3.12. _(environmental; not a Phase 4 code defect.)_
- `apply_migrations.py` and `infra_bootstrap.sh` are git-ignored (`.gitignore:8–9`): their on-disk content is secret-free (AC 7 holds substantively) but their edits are not version-controlled and do not appear in the reviewable diff. This is a pre-existing repo condition, not introduced by Phase 3. _(context.)_
- Adding `sentence-transformers` pulls in `torch` (CPU). This is a local model, not an LLM/model-API dependency, and is the intended mechanism for AC 8; it is sized for no-GPU school servers and loaded once at lifespan. _(data.)_
