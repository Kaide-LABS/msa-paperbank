# What OSA got done before it stopped

## In short
- We will move the PAU past-paper bot off Google Cloud so the school can run it on its own Linux servers.
- The bot will run in Docker with a local Postgres, store files on disk or MinIO, and hand out short-lived download links.
- Search will use a small CPU model that runs on the school's hardware instead of Google's Vertex AI, with no change in what users get.
- WhatsApp keeps working; the code is reshaped so a future Teams agent can plug in later without touching GCP.
- You'll know it works when the existing tests still pass, a before/after search comparison matches, and the whole thing starts with one Docker Compose command.

## It did not finish
The finished project did not pass the final check against the requirements.

## Stage by stage

### Stage 1
#### What was built

The bot's inner workings were reshaped so that the parts that talk to Google's cloud — file storage, search, password-style secrets, and the database connection — now go through tidy "plug points" instead of being wired directly to Google. Today's behaviour is unchanged and Google is still the only thing plugged in, but the groundwork is now laid so the school's own tools can be slotted in next, without rewriting the bot. New safety-check tests and a short explainer document were added to lock this in.

#### What was decided

Only the main, live path was switched over this stage, to keep the change small and safe. One older, unused side-path was deliberately left for a later stage. Google's current behaviour was copied exactly rather than improved, to avoid any surprises for users.

#### What is uncertain

The full set of safety checks could not all be run here because this workstation runs a mismatched version of the underlying software; the focused checks passed. This must be confirmed on the project's proper setup before relying on it. Also, one older side-path still points at the old wiring and would fail if used; it is flagged for the next stage.

### Stage 2
#### What was built

The bot's "brain" was separated from the part that talks to WhatsApp. Before, the two were tangled together; now there's a clean middle layer that takes in a message, works out the answer, and sends a reply — without caring which app the message came from. WhatsApp still works exactly as before. Because of this split, a future Microsoft Teams version can be added later without disturbing anything. The way files are labelled in storage was also renamed to remove old Google-specific names, with a documented way to undo it.

#### What was decided

The old WhatsApp wiring was kept in place as a safety net rather than deleted, so nothing existing breaks. The storage rename was made reversible, to keep it safe. User experience was left completely unchanged, because this stage was plumbing, not features.

#### What is uncertain

Three loose ends were found and are scheduled to be fixed in the next stage: a few places still use the old storage labels and would fail when looking up files, and a planned safety test was not written yet. Also, the full test suite could not be run here due to a software-version mismatch, so final confirmation that everything passes is still pending.

### Stage 3
#### What was built

The bot can now store files on the school's own system and hand out download links that work for a short time, then expire — so files stay private without relying on Google. A new rule also makes sure only approved requests can ask the bot for a paper. This replaces parts that previously depended on Google's cloud.

#### What was decided

Download links were made to expire quickly and be tamper-proof, for safety. Old Google-specific account details were stripped out of the setup files, so nothing is tied to Google by accident. Where a choice existed, the team favoured settings that keep the system locked-down by default.

#### What is uncertain

This stage finished, but with gaps that need attention. The full set of safety checks could not all be run here because of a mismatch in the testing environment — they must be re-run on the school's proper setup before trusting the result. One planned automatic check that guards against leftover Google details was not written yet. And the real before-and-after search comparison still has to be done on the live collection later by an operator.

### Stage 4
#### What was built

The bot can now run its own search engine on the school's own computers, instead of renting Google's. A new piece reads a question and finds the most relevant past papers using a small program that runs on ordinary hardware. We also built a tool that re-does the search index for every stored paper, and a side-by-side checker that compares the new search results against the old Google ones to confirm people still get the same answers.

#### What was decided

We kept the search quality the same size and shape as before, so users notice no difference. We fixed a flaw in the re-indexing tool that would have rebuilt the index incorrectly. We also added an automatic check that scans our own files for leaked passwords or old Google account details, to catch mistakes early.

#### What is uncertain

This stage is finished, but a few things need attention. The full set of tests has only been confirmed on a slightly different setup than the school's real one, so it should be re-checked there. More importantly, the bot cannot yet start up on the school's servers without still reaching for Google — fixing that is the next stage's job. One internal log accidentally recorded sensitive-looking text.

### Stage 5
#### What was built

The bot can now be started on the school's own computers with a single command. Everything it needs to run — the bot, its database, its file storage, and its search brain — now starts up together as one package. The search brain is a small model that runs on the school's own hardware, so the bot no longer depends on Google for searching. There are also new tools to make nightly safety copies of the data and to restore from them if needed, plus written guides for starting it up and keeping it running securely over the internet.

#### What was decided

Search was switched to a self-contained model so users get the same results without relying on Google. File storage can use either the plain hard disk or an optional add-on, kept simple by default. Safety copies refuse to run against the live system, to avoid accidents.

#### What is uncertain

The stage finished, but some checks still need a real server. Nobody has yet started the full package on an actual school computer to confirm it runs without Google. The complete automated test run also needs confirming on the proper setup. One optional storage add-on may not report itself as "ready" correctly.

### Stage 6
#### What was built

The tools to actually move the bot off Google and onto the school's own servers now exist, and the bot's own code no longer depends on Google at all. There's a step-by-step moving kit: copy the data across, rebuild the search index on the school's hardware, and check the new search gives the same answers as the old one. All the Google-specific parts have been stripped out, and the bot now defaults to running entirely on the school's own equipment.

#### What was decided

The moving tools won't touch the live system until someone signs a go-ahead note, and they only read (never change) the old Google setup — to prevent accidents. By default, nothing runs against the real data until explicitly confirmed, as a safety measure.

#### What is uncertain

The moving kit has been written and tested, but **the actual move has not happened yet** — it waits for your sign-off. The full set of checks has only been run in a stand-in testing setup, not yet on a real school server or the real Docker setup. Someone still needs to confirm everything starts up and works cleanly on the school's actual hardware before going live.

## Choices made for you
- (you confirmed this risky one) The local CPU embedder uses a sentence-transformers / Hugging Face model with native 768-dim output (e.g. all-mpnet-base-v2 class), run via sentence-transformers or ONNX Runtime; exact model chosen to maximise top-k parity.
- (you confirmed this risky one) The top-k parity harness passes if new-vs-old top-k result sets meet a defined overlap/rank-correlation threshold on the fixed query set; the threshold is proposed in the report since the prompt specifies the check but not a number.
- (you confirmed this risky one) ObjectStore defaults to local filesystem for development and MinIO is optional/for production, selected by configuration.
- (you confirmed this risky one) The future tool endpoint uses a static bearer/shared-secret token for auth now, with a view to Copilot Studio-compatible auth later.
- (you confirmed this risky one) The authoritative tree is the root-level codebase (app/, admin/, review/, cloud_ingest/, scripts/, migrations/, tests/); any nested msa-paperbank/ mirror is not edited.
- (you confirmed this risky one) Column rename uses Alembic (the existing migrations/ tooling) for the reversible migration carrying the SQLAlchemy synonyms.
- (you confirmed this risky one) Making the daily model cost-cap breaker 'harmless' means turning it into a no-op/removing it, since the backend no longer calls any paid model API.
- This phase just reorganizes the existing system internally — nothing changes in how it behaves, and it keeps running exactly as it does today.
- It still runs only on the current cloud provider; the groundwork for switching to other options is laid, but none are available yet.
- If someone sets up the system with an unsupported provider name, it stops immediately with a clear error rather than misbehaving.
- No new outside services, costs, or network connections are added, and nothing contacts the internet just from starting the system up.
- The reorganization is structured so each piece — file storage, the text-understanding model — can be swapped out one at a time in later phases cleanly, with minimal rework.
- Several planned capabilities (shareable file links, running without the cloud, the alternative storage option) are deliberately left for later phases.
- Existing safeguards and the daily spending limit are left exactly as they are for now, to be revisited later.
- All existing automated checks continue to pass unchanged, confirming nothing was broken.

## How it was checked
- Research: 71 official documentation source(s), 5 academic paper(s) and 0 existing project(s) were consulted.
- A second, different AI checked the research against its sources.
- Every build stage was written by one AI and reviewed by a different one, and every change was recorded in git.

## Does it actually work?
- 7 of 14 requirements were seen working when the finished project was run.
- Not working / not shown: The existing pytest suite passes unchanged after Phase 1 (tests minimally re-pointed at new seams are allowed; no behavioural assertion changed).
- Not working / not shown: Ports exist for object store, embedder, secrets, and DB engine, selectable by a provider setting, with the existing GCP implementations behind them.
- Not working / not shown: The gcs_* rename is applied via a reversible migration using SQLAlchemy synonyms, and the pre-existing env variable names still resolve.
- Not working / not shown: No plaintext DB password, Cloud SQL connection string, or hardcoded GCP project id remains in apply_migrations.py, scripts, or the Dockerfile.
- Not working / not shown: A re-embed job repopulates chunk and title embeddings, and a recorded parity report compares old vs new top-k results on a fixed query set.
- Not working / not shown: docker compose up starts bot + Postgres (pgvector, pg_trgm) + optional MinIO, and each service reports healthy via its health check.
- Not working / not shown: Phase 6 migration/cutover/teardown scripts exist but are not executed, and GCP production remains running and reversible. (the check could not exercise this criterion)

## What to look at
- opencode-cli is installed and signed in but did not answer a test call (opencode-cli: The AI provider's reply wasn't in the expected form.), so it was left out. If its default model is not available to your account, name one in osa.config.json: providers.modelOverrides.
- antigravity-cli also answered, but OSA only chooses providers it has run builds on by itself (claude-code, codex-cli) unless they are the only ones; name it in providers.pair to use it.
- OSA chose claude-code and codex-cli from the providers that are installed and signed in.
- claude-code reviewed work written by codex-cli: a different model family, the most independent kind of check.
- This run was carried on from its saved spec: intake, research and spec were not repeated.
- The build was carried on from phase 6: phases 1 to 5 were already finished and kept. 2 commit(s) from the interrupted attempt were folded back into the working tree so the reviewer still sees that work.

## For engineers (technical detail)

_Everything above is written for non-engineers; this is the raw detail behind it._

- `decision: The authoritative codebase is the root-level tree ('app/', 'admin/', 'review/', 'cloud_ingest/', 'scripts/', 'migrations/', 'tests/', 'apply_migrations.py'); the nested 'msa-paperbank/' directory is a stale partial mirror and is NOT edited in any phase.`
- `decision: Ports live in a new 'app/ports.py' as 'typing.Protocol' classes (structural, not ABCs); GCP adapters live in a new 'app/providers/gcp/' package; a factory in 'app/providers/__init__.py' selects implementations by a new setting.`
- `decision: The provider setting is named 'provider' (env 'PROVIDER'), added to 'app/config.Settings' with default '"gcp"'. This phase only '"gcp"' is a valid value; '"local"'/'"minio"' arrive in later phases. An unknown value raises 'ValueError' at factory call time.`
- `decision: Phase 1 is a pure refactor with GCP implementations only: no new runtime dependencies, no new network calls, no behaviour change. No Azure, no local embedder, no MinIO, no signed URLs this phase.`
- `decision: The 'ObjectStore' port this phase exposes 'download_bytes'/'upload_bytes'/'exists'/'delete' only (the exact GCS operations the code uses today). 'signed_url' is deferred to Phase 3.`
- `decision: The 'Embedder' port mirrors 'app.embeddings' ('embed_one', 'embed_query', 'embed_documents') plus a 'dim' property; 'GcpEmbedder' delegates to the existing 'app.embeddings' functions by lazy import (no logic duplication), preserving 'task_type' RETRIEVAL_QUERY/RETRIEVAL_DOCUMENT and the dimension check.`
- `decision: The 'gcs_object' DB columns and the 'gcs_bucket'/'media_gcs_prefix'/'*_gcs_prefix' settings keep their names this phase; the neutral 'object_key' rename is Phase 2 (per the PRD), so the storage port is provider-neutral regardless of these legacy names.`
- `decision: The secrets provider is selected by a direct 'os.environ' read (not via 'Settings') to avoid the secrets-load-before-settings bootstrap and a config↔providers circular import; it preserves the existing 'GCP_LOAD_FROM_SECRETS' / '*_FROM_SECRET' behaviour exactly.`
- `decision: Adapters instantiate their underlying GCP clients lazily (on first use / via 'from_settings'), never at module import, so importing any provider module makes no network call.`
- `decision: The existing test that patches 'admin.curate.storage.Client' may be minimally re-pointed at the new store seam; no behavioural assertion is changed. This counts as satisfying "existing pytest passes unchanged."`
- `decision: The 'DATABASE_URL_TEST'/sqlite pytest branch in 'app/db.py' and 'tests/conftest.py' is preserved unchanged; only the non-test Cloud SQL engine construction is routed through the engine-provider port.`
- `decision: The daily cost-cap breaker is left untouched this phase (the PRD's "make harmless or remove" is not a provider seam); it is addressed in a later phase.`
- `decision: Architecture: kept the original plan after an independent review -- The ports-and-adapters layer is load-bearing for two specific PRD mechanics the alternatives all weaken. The phased plan swaps implementations independently — object store in Phase 3, embedder in Phase 4 — which Alt 3's bundled 'Environment' makes awkward (mixed GCP-secrets/local-storage states mid-migration) and Alt 1's scattered per-site branches turn into repeat call-site churn each phase. AC 12/13's "clean delete of all GCP code" is a one-line 'rm -rf app/providers/gcp/' under the plan but a diff-by-diff audit ac`
- `tokens (estimated): 229515 total -- file_exploration 25%, research_input 0%, handoffs 9%, spec_prd 12%, tool_output 47%, model_output 8%`
