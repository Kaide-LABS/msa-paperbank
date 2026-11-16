# What OSA got done before it stopped

## In short
- We will move the PAU past-paper bot off Google Cloud so the school can run it on its own Linux servers.
- The bot will run in Docker with a local Postgres, store files on disk or MinIO, and hand out short-lived download links.
- Search will use a small CPU model that runs on the school's hardware instead of Google's Vertex AI, with no change in what users get.
- WhatsApp keeps working; the code is reshaped so a future Teams agent can plug in later without touching GCP.
- You'll know it works when the existing tests still pass, a before/after search comparison matches, and the whole thing starts with one Docker Compose command.

## It did not finish
The build stopped before it was finished.

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

### Stage 4 (did not complete)
#### What was built

Nothing new is working yet from this stage. The goal was to swap the bot's search engine over to a small program that runs on the school's own computers — so searches no longer depend on Google — while keeping the results people see exactly the same. This stage was meant to deliver that change, but it did not get there.

#### What was decided

The plan is to run the new search on the school's own hardware rather than a paid Google service, so the school controls its own system and costs. The intended safeguard was to compare searches before and after the switch to confirm users notice no difference.

#### What is uncertain

This stage did not complete. The automated helper doing the work stopped partway through with an error and could not continue, so the search change was not finished or tested. Nothing was broken, but nothing was proven either. This needs attention: the work has to be restarted and run again before we can trust the new search, and before we can say the before-and-after comparison truly matches.

## Choices made for you
- (you confirmed this risky one) The local CPU embedder uses a sentence-transformers / Hugging Face model with native 768-dim output (e.g. all-mpnet-base-v2 class), run via sentence-transformers or ONNX Runtime; exact model chosen to maximise top-k parity.
- (you confirmed this risky one) The top-k parity harness passes if new-vs-old top-k result sets meet a defined overlap/rank-correlation threshold on the fixed query set; the threshold is proposed in the report since the prompt specifies the check but not a number.
- (you confirmed this risky one) ObjectStore defaults to local filesystem for development and MinIO is optional/for production, selected by configuration.
- (you confirmed this risky one) The future tool endpoint uses a static bearer/shared-secret token for auth now, with a view to Copilot Studio-compatible auth later.
- (you confirmed this risky one) The authoritative tree is the root-level codebase (app/, admin/, review/, cloud_ingest/, scripts/, migrations/, tests/); any nested msa-paperbank/ mirror is not edited.
- (you confirmed this risky one) Column rename uses Alembic (the existing migrations/ tooling) for the reversible migration carrying the SQLAlchemy synonyms.
- (you confirmed this risky one) Making the daily model cost-cap breaker 'harmless' means turning it into a no-op/removing it, since the backend no longer calls any paid model API.
- We're setting up the system so its major pieces (where files are stored, how documents are understood) can be swapped out later without disrupting everything — this is groundwork for moving away from Google's cloud.
- This round changes nothing about how the system behaves: same features, same speed, nothing new added and nothing removed that users would notice.
- No new outside services, costs, or internet connections are introduced in this round — it's purely internal tidying.
- A new setting picks which provider to use; for now only Google is allowed, with other options (running on your own machine) coming in later rounds. Choosing an unsupported option fails immediately rather than misbehaving.
- Work continues in the main, up-to-date version of the project; an old leftover copy is deliberately left alone to avoid confusion.
- Each piece only connects to the outside when actually used, so routine startup and testing stay fast and offline.
- Existing safety checks and tests are kept as-is, so we can be confident nothing quietly broke.
- We deliberately kept the original plan: it makes the later switch-over clean and simple for the school's IT staff, avoiding a more complex setup that would be harder to run and maintain.

## How it was checked
- Research: 71 official documentation source(s), 5 academic paper(s) and 0 existing project(s) were consulted.
- A second, different AI checked the research against its sources.
- Every build stage was written by one AI and reviewed by a different one, and every change was recorded in git.

## What to look at
- antigravity-cli also answered, but OSA only chooses providers it has run builds on by itself (claude-code, codex-cli) unless they are the only ones; name it in providers.pair to use it.
- OSA chose claude-code and codex-cli from the providers that are installed and signed in.
- claude-code reviewed work written by codex-cli: a different model family, the most independent kind of check.
- This run was carried on from its saved spec: intake, research and spec were not repeated.
- The build was carried on from phase 4: phases 1 to 3 were already finished and kept. 5 commit(s) from the interrupted attempt were folded back into the working tree so the reviewer still sees that work.

## For engineers (technical detail)

_Everything above is written for non-engineers; this is the raw detail behind it._

- `Phase 4's own runDispatch() call did not complete successfully: claude-code: The AI provider stopped with an error (it exited with code 1)..`
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
- `tokens (estimated): 24937 total -- file_exploration 15%, research_input 0%, handoffs 24%, spec_prd 52%, tool_output 2%, model_output 6%`
