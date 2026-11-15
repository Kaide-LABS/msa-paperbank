# Research report -- Migrate a FastAPI WhatsApp retrieval bot from GCP/Vertex to Azure with provider-neutral seams, reversibly

Generated 2026-11-02T09:37:47.247Z by OSA. Researched by claude-code using its built-in web search. Time range: last 18 months, prioritising current state as of Nov 2026.
Values marked [uncertain] could not be verified from a source the agent opened; they are repeated under *Open uncertainties*.

## Findings

### Official documentation: Azure OpenAI Service
*Find the OFFICIAL documentation for "Azure OpenAI Service": its current stable version, how it is installed or enabled, the API surface this build will use, and any breaking changes or pitfalls in the last 18 months, prioritising current state as of Nov 2026.*

Azure OpenAI Service's officially documented current state (as of docs dated through mid/late 2026) centers on the new 'v1' data-plane API (GA since August 2025), which drops the monthly dated `api-version` query parameter in favor of a stable `/openai/v1/` base path, while the older dated-version API (latest GA `2024-10-21` for image/audio, `2024-06-01` historically for chat/embeddings/completions) remains supported for backward compatibility. For this build, the relevant surface is `chat.completions.create`/`responses.create` with `image_url` content parts on a vision-capable model (e.g. gpt-4o-class) for OCR of scanned past papers, and `embeddings.create` with a `text-embedding-3-small`/`-large` deployment plus the `dimensions` request parameter set to 768 to match the existing pgvector column. Authentication is via API key (`api-key` header) or Microsoft Entra ID (`Cognitive Services OpenAI User` role + bearer token), both documented in the official Microsoft Learn reference. The most significant recent breaking change is the v1 API's new base_url/client pattern (OpenAI() client instead of AzureOpenAI(), no api-version needed) introduced in Aug 2025; the older SDK/date-versioned pattern still works but is the 'classic' path.

**Key findings**
- The Azure OpenAI 'v1' data-plane API became GA starting August 2025, removing the need for monthly dated `api-version` values and allowing use of the plain `OpenAI()` client pointed at `https://YOUR-RESOURCE-NAME.openai.azure.com/openai/v1/` [learn.microsoft.com/azure/foundry/openai/api-version-lifecycle, ms.date 2026-05-13].
- Dated API versioning still exists in parallel: latest GA dated release for image/audio is `2024-10-21`; a `v1 preview` track also exists for newer preview-only features [learn.microsoft.com/azure/foundry/openai/reference].
- Embeddings endpoint (`POST {endpoint}/openai/v1/embeddings`) officially documents a `dimensions` integer parameter, 'Only supported in text-embedding-3 and later models', min constraint 1 — confirms 768-dim output is achievable via `dimensions=768` on text-embedding-3-small/large without re-architecting the Vector(768) column [learn.microsoft.com/rest/api/microsoft-foundry/azureopenai/embeddings].
- Embeddings limits: 8,192 max input tokens per item, max 2,048 items per array request, and a hard 300,000-token aggregate cap per request (HTTP 400 if exceeded) [learn.microsoft.com/azure/foundry/openai/how-to/embeddings, ms.date 2026-07-22].
- Vision-enabled chat models use the standard chat completions endpoint with image content parts; dedicated doc page 'How to use vision-enabled chat models' covers calling the Chat Completion API and processing images [learn.microsoft.com/azure/foundry/openai/how-to/gpt-with-vision, ms.date 2026-07-29].
- Breaking change (within the broader lifecycle, pre-dating 18mo window but still load-bearing): the `2024-04-01-preview` spec removed the `enhancements` parameter, impacting the `gpt-4` `vision-preview` model — anything still depending on that legacy vision-preview param path breaks [learn.microsoft.com/azure/foundry/openai/api-version-lifecycle].
- Known API Management issue: the `2025-04-01-preview` Azure OpenAI spec uses OpenAPI 3.1, which Azure API Management doesn't fully support yet — relevant if fronting Azure OpenAI with APIM [learn.microsoft.com/azure/foundry/openai/api-version-lifecycle].
- Authentication: API key via `api-key` header, or Microsoft Entra ID via bearer token with `Cognitive Services OpenAI User` RBAC role; the v1 API client supports automatic token refresh natively without a separate Azure-specific client class [learn.microsoft.com/azure/foundry/openai/api-version-lifecycle].
- Control-plane (resource/deployment management, e.g. for Bicep) latest GA is `2025-06-01`; this is the ARM-facing API, distinct from the data-plane inference API [learn.microsoft.com/azure/foundry/openai/reference].

**Recommendations**
- Build the Azure LLM/vision/embedding adapter against the v1 API (`base_url=.../openai/v1/`, plain `OpenAI()` client) rather than the legacy dated `AzureOpenAI()` client, since it is now the GA, forward-looking surface and simplifies auth/token-refresh code.
- Use Microsoft Entra ID (`DefaultAzureCredential` + `get_bearer_token_provider`) for the secrets/config seam instead of static API keys, matching the officially recommended pattern and avoiding a secret in the repo/config.
- For embeddings, explicitly pass `model="text-embedding-3-small"` (or `-large`) and `dimensions=768` to preserve the existing Vector(768)/HNSW schema — do not assume a different model's default dimension matches.
- Batch embedding calls to respect the 300,000-token aggregate and 2,048-item array limits; chunk the re-embedding backfill job accordingly.
- For the OCR A/B gate, implement the Azure path via chat completions with image content parts on a vision-capable deployment per the official 'gpt-with-vision' how-to, not via a deprecated `vision-preview`/`enhancements`-parameter path (removed in `2024-04-01-preview`).
- If any component fronts Azure OpenAI through Azure API Management, avoid relying on the `2025-04-01-preview` spec import until APIM's OpenAPI 3.1 support matures; prefer GA/v1 specs for APIM import.
- Treat the `dimensions`/embeddings-limits facts as verified-current (opened official docs); treat anything about GPT-5-class vision model names/pricing as needing a fresh check against the Models/pricing page close to implementation time, since model catalogs change faster than the API surface.

**current version:** v1 (GA, opt-in since August 2025) for the data-plane inference API; legacy dated API versions remain supported with latest GA dated release 2024-10-21 (image/audio) — [uncertain] exact latest dated GA for chat/embeddings text ops beyond what's superseded by v1

**api surface**
- POST {endpoint}/openai/v1/chat/completions (or client.chat.completions.create / client.responses.create) with image_url content parts for vision OCR
- POST {endpoint}/openai/v1/embeddings (client.embeddings.create) with model=text-embedding-3-small|large and dimensions=768
- Auth: api-key header, or Authorization: Bearer <Entra ID token> via DefaultAzureCredential + get_bearer_token_provider, scope https://ai.azure.com/.default or https://cognitiveservices.azure.com/.default
- RBAC role 'Cognitive Services OpenAI User' for Entra ID callers
- Control-plane ARM/Bicep deployment API (latest GA 2025-06-01) for provisioning the Foundry/Azure OpenAI resource and model deployments

**pitfalls**
- v1 API (Aug 2025 GA) changes the client pattern entirely (OpenAI() instead of AzureOpenAI(), base_url with /openai/v1/, no api-version needed) — mixing old and new patterns in the same codebase will confuse the provider-neutral seam; pick one pattern per adapter.
- `dimensions` parameter on embeddings only works on text-embedding-3-and-later models; using it against an older/unsupported embedding model returns a 422 [uncertain, sourced from secondary summary, not directly quoted from an opened official page listing the 422 behavior].
- Embeddings aggregate 300,000-token-per-request and 2,048-items-per-array limits can silently break large backfill/re-embed batch jobs if not chunked.
- `enhancements` parameters were removed in 2024-04-01-preview, breaking the old gpt-4 vision-preview flow — don't follow stale blog examples using that parameter for OCR.
- OpenAI Python SDK 0.x -> 1.x was itself a breaking rewrite (engine= -> model=, openai.ChatCompletion.create -> client.chat.completions.create, embeddings_utils.py removed); any older code samples/snippets found online may target the pre-1.x SDK and silently fail.
- Azure API Management has a known compatibility gap with the 2025-04-01-preview spec's OpenAPI 3.1 — avoid importing that spec version into APIM if the bot is fronted by APIM.
- Control-plane (ARM/Bicep) API versioning is separate from data-plane inference versioning — don't conflate the two when writing Bicep for Container Apps/ACR vs. runtime SDK calls.

*As of: Documentation pages fetched carry ms.date/updated_at stamps from 2026-05-13 through 2026-07-29; v1 API went GA August 2025. Treat as current for Nov 2026.*

**Sources**
- [Azure OpenAI in Microsoft Foundry Models v1 API (API evolution / lifecycle)](https://learn.microsoft.com/en-us/azure/foundry/openai/api-version-lifecycle) (official-docs) -- "Starting in August 2025, you can opt in to the next generation v1 Azure OpenAI APIs which add support for: Ongoing access to the latest features with no need to specify new api-version's each month..."
- [Azure OpenAI image and audio REST API reference (2024-10-21) - Microsoft Foundry](https://learn.microsoft.com/en-us/azure/foundry/openai/reference) (official-docs) -- "There is now a new preview inference API... | Data plane | v1 preview | v1 | ... | The data plane API controls inference and authoring operations."
- [Microsoft Foundry REST Reference - Azure OpenAI - Embeddings](https://learn.microsoft.com/en-us/rest/api/microsoft-foundry/azureopenai/embeddings) (official-docs) -- "dimensions | integer | The number of dimensions the resulting output embeddings should have. Only supported in text-embedding-3 and later models. Constraints: min: 1"
- [Generate embeddings with Azure OpenAI - Microsoft Foundry](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/embeddings) (official-docs) -- "Embedding requests return HTTP 400 when the sum of input tokens exceeds 300,000... The maximum input length for the current embedding models is 8,192 tokens... maximum array size is 2,048."
- [How to use vision-enabled chat models - Microsoft Foundry](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/gpt-with-vision) (official-docs) -- "Learn how to use vision-enabled chat models in Azure OpenAI, including how to call the Chat Completion API and process images."
- [Azure OpenAI API version changelog (within api-version-lifecycle)](https://learn.microsoft.com/en-us/azure/foundry/openai/api-version-lifecycle) (official-docs) -- "Breaking Change: Enhancements parameters removed. This change impacts the gpt-4 Version: vision-preview model."
- [How to migrate to OpenAI Python v1.x (classic) - Microsoft Foundry (classic)](https://learn.microsoft.com/en-us/azure/foundry-classic/openai/how-to/migration) (official-docs) -- "Upgrading from version 0.28.1 to version 1.x is a breaking change, you'll need to test and update your code... This guidance is no longer recommended. To take advantage of the latest v1 API refer to the Python programming language guide."


### Official documentation: Microsoft Foundry (Azure AI Foundry)
*Find the OFFICIAL documentation for "Microsoft Foundry (Azure AI Foundry)": its current stable version, how it is installed or enabled, the API surface this build will use, and any breaking changes or pitfalls in the last 18 months, prioritising current state as of Nov 2026.*

Microsoft Foundry (rebranded from Azure AI Foundry) is Microsoft's unified AI platform combining model deployment, agents, and an OpenAI-compatible Responses API; the current Python surface is the `azure-ai-projects` SDK (>=2.3.0, the 'Foundry projects (new) API') talking to an `AIProjectClient` at `https://<resource>.services.ai.azure.com/api/projects/<project>`. For this build's OCR/vision needs, the relevant official surface is either Azure OpenAI vision via `openai.responses.create()` through the Foundry project's OpenAI-compatible client, or Azure AI Document Intelligence (now 'Foundry Tools') REST API 2024-11-30 (v4.0 GA) using the `prebuilt-layout`/`prebuilt-read` models. Both are authenticated with Entra ID (`DefaultAzureCredential`), avoiding static API keys in the repo. The platform underwent a late-2025/2026 rebrand that split documentation into a 'classic' (1.x SDK) tree and a current tree (2.x SDK, incompatible with 1.x) — the build must target the current 2.x docs and 2024-11-30 Document Intelligence API, not the classic/legacy versions.

**Key findings**
- Official quickstart (learn.microsoft.com/azure/foundry/quickstarts/get-started-code, updated 2026-10-19) specifies Python install: `pip install "azure-ai-projects>=2.3.0"`, authenticated via `DefaultAzureCredential` from `azure-identity`.
- Project endpoint format is `https://<resource-name>.services.ai.azure.com/api/projects/<project-name>`.
- Core client pattern: `AIProjectClient(endpoint=..., credential=DefaultAzureCredential())`, then `project.get_openai_client()` returns an OpenAI-compatible client used as `openai.responses.create(model=..., input=...)`.
- The docs explicitly state: 'Code uses Azure AI Projects 2.x and is incompatible with Azure AI Projects 1.x' — 1.x lives under the separate 'foundry-classic' documentation tree.
- Agents are created via `project.agents.create_version(agent_name=..., definition=PromptAgentDefinition(model=..., instructions=...))`; multi-turn chat uses `openai.conversations.create()` plus `responses.create(conversation=conversation.id, input=...)`.
- Document Intelligence (official 'what's new' page, learn.microsoft.com/.../document-intelligence/whats-new, dated 2026-06-11, last updated 2026-10-19): current stable/GA REST API is 2024-11-30 (v4.0); v2.1 reaches end of support 2027-09-15, v3.0 (2022-08-31) reaches end of support 2029-03-30 — new development should target 2024-11-30.
- The general-purpose `prebuilt-document` model was deprecated as of the 2023-10-31-preview API; key-value extraction should instead use `prebuilt-layout` with `features=keyValuePairs`.
- Document Intelligence v4.0 Layout and Read container images became available April 2025 and June 2025 respectively, per the official changelog.
- Analyze responses from Document Intelligence are retained only 24 hours by default after completion unless explicitly deleted/persisted — relevant if the OCR A/B gate needs to re-check raw outputs later.
- Azure AI Foundry was renamed 'Microsoft Foundry' around Microsoft Ignite in November 2025, with product-terms/doc-URL changes formalized into early 2026; I could not open an official Microsoft Learn page that itself announces/dates this rename, so the exact effective date comes from secondary industry-analyst coverage, not a primary source I opened. [uncertain]
- Document Intelligence per-page pricing (e.g. ~$1.50/1,000 pages for Read/OCR cited by third-party aggregators) could not be confirmed on the official azure.microsoft.com pricing page, which renders prices dynamically per region/currency and showed only placeholder dashes when fetched. [uncertain]

**Recommendations**
- Pin the OCR/vision abstraction's Azure implementation to `azure-ai-projects>=2.3.0` and the current (non-classic) Foundry docs/SDK; do not mix in 1.x ('classic') samples or package versions, since the two are documented as incompatible.
- For the OCR A/B gate, implement the Azure side as two swappable backends behind the same interface: (a) Azure OpenAI vision via `AIProjectClient.get_openai_client().responses.create()` with multimodal image input, and (b) Azure AI Document Intelligence `prebuilt-layout`/`prebuilt-read` via REST API version 2024-11-30 — let the gate pick whichever meets the accuracy bar vs Gemini.
- Use `prebuilt-layout` (with `features=keyValuePairs` if structured fields are needed) rather than the deprecated `prebuilt-document` model.
- Authenticate via Entra ID / `DefaultAzureCredential` (managed identity in Container Apps) rather than embedding Foundry or Document Intelligence keys, consistent with the 'no secrets in repo' constraint.
- When populating pricing.py with Azure model/OCR costs, pull exact per-unit prices from the Azure Pricing Calculator or the Azure portal rather than scraping the static pricing page, since that page is JS-rendered with placeholders.
- If retention of raw OCR analyze responses beyond 24 hours is needed for audit/parity comparisons, persist results to Blob storage immediately after each `analyze` call rather than relying on the service's own 24-hour retention.
- Treat the Nov 2025/2026 Azure AI Foundry → Microsoft Foundry rebrand as a documentation/terminology shift only — verify any cached or memory-based references to 'Azure AI Foundry' package names or URLs against the current docs tree before reuse, since classic vs current paths diverge.

**current version:** Python SDK: azure-ai-projects >=2.3.0 (Foundry projects 'new'/2.x API); Azure AI Document Intelligence REST API: 2024-11-30 (v4.0, GA)

**api surface**
- azure.ai.projects.AIProjectClient(endpoint, credential=DefaultAzureCredential())
- AIProjectClient.get_openai_client() -> OpenAI-compatible client; openai.responses.create(model=..., input=...) for text/vision chat completions
- AIProjectClient.agents.create_version(agent_name, definition=PromptAgentDefinition(model, instructions)) (only if agent framing is used)
- Document Intelligence REST API 2024-11-30: POST {endpoint}/documentintelligence/documentModels/prebuilt-layout:analyze?api-version=2024-11-30 (and prebuilt-read for plain OCR)
- azure-identity DefaultAzureCredential for Entra ID auth (managed identity in Container Apps, az login locally)
- Endpoint format: https://<resource-name>.services.ai.azure.com/api/projects/<project-name>

**pitfalls**
- azure-ai-projects 2.x is explicitly documented as incompatible with 1.x ('classic') — mixing samples/packages across the two will break at runtime.
- Document Intelligence v2.1 and v3.0 REST APIs are legacy/retiring (Sept 2027 and Mar 2029 respectively); any new integration must target the 2024-11-30 v4.0 API.
- prebuilt-document model is deprecated since the 2023-10-31-preview API; use prebuilt-layout with features=keyValuePairs instead.
- Document Intelligence analyze results are only retained 24 hours by default — persist results elsewhere if needed for later OCR parity auditing.
- Instant/preview models (e.g. gpt-5-mini 'instant access') were, per the official quickstart, only available in the West US 3 region during preview — region choice in Bicep parameters matters.
- The late-2025 rename from 'Azure AI Foundry' to 'Microsoft Foundry' split documentation into a 'classic' tree and a current tree with different URLs and SDK versions; stale bookmarks/snippets referencing the old name may point at the classic (1.x) docs. [uncertain]
- Document Intelligence pricing is not available as static text on the official pricing page (JS-rendered placeholders); relying on scraped/third-party numbers for pricing.py risks drift from actual billed rates. [uncertain]

*As of: 2026-11-02; primary pages dated/updated 2026-10-19 (Foundry quickstart), 2026-08-05/2026-08-07 (Foundry classic SDK overview), 2026-06-11/2026-10-19 (Document Intelligence what's new)*

**Sources**
- [Quickstart: Get started with Microsoft Foundry SDK - Microsoft Foundry | Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/quickstarts/get-started-code) (official-docs) -- "Install the current version of `azure-ai-projects`. This version uses the Foundry projects (new) API... pip install "azure-ai-projects>=2.3.0"... Code uses Azure AI Projects 2.x and is incompatible with Azure AI Projects 1.x."
- [Get started with Microsoft Foundry SDKs and endpoints (classic) - Microsoft Foundry (classic) portal | Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry-classic/how-to/develop/sdk-overview?pivots=programming-language-python) (official-docs) -- "ms.service: microsoft-foundry ... Learn how to choose Microsoft Foundry SDKs and endpoints, configure a project endpoint, and start building AI applications in the classic experience."
- [What's new in Document Intelligence - Foundry Tools | Microsoft Learn](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/whats-new?view=doc-intel-4.0.0) (official-docs) -- "Document Intelligence REST API v2.1 reaches end of support on September 15, 2027... use Azure Document Intelligence 2024-11-30 v4.0 for all new development... the general document model (prebuilt-document) is deprecated."
- [Azure Document Intelligence Pricing (vendor pricing page, dynamically rendered)](https://azure.microsoft.com/en-us/pricing/details/ai-document-intelligence/) (official-docs) -- "pricing tables contain placeholder values indicated by dashes... now called 'Azure Document Intelligence in Foundry Tools'"
- [Foundry Gets New Name, Anthropic Models - Directions on Microsoft](https://www.directionsonmicrosoft.com/reports/foundry-gets-new-name-anthropic-models/) (article) -- "Foundry Gets New Name... (Microsoft Ignite rebrand coverage)"
- [Azure AI Document Intelligence Pricing 2026: From $1.50](https://www.erpresearch.com/erp-add-ons/ocr/azure-document-intelligence/pricing) (article) -- "Azure AI Document Intelligence starts at $1.50 per 1,000 pages (Read/OCR); $10 per 1,000 prebuilt; $30 per 1,000 custom."


### Official documentation: Azure AI Document Intelligence
*Find the OFFICIAL documentation for "Azure AI Document Intelligence": its current stable version, how it is installed or enabled, the API surface this build will use, and any breaking changes or pitfalls in the last 18 months, prioritising current state as of Nov 2026.*

Azure AI Document Intelligence (formerly Form Recognizer, now also branded under 'Azure AI Foundry Tools') is GA at API version 2024-11-30 (v4.0), the current stable version for all new development as of Nov 2026. It is provisioned as a Cognitive Services resource (single-service 'Document Intelligence' or multi-service Foundry resource) via the Azure Portal, authenticated with an API key (AzureKeyCredential) or Azure AD/managed identity (DefaultAzureCredential), and accessed via the Python package azure-ai-documentintelligence using DocumentIntelligenceClient.begin_analyze_document('prebuilt-read', ...). For this build's OCR A/B gate, the relevant surface is the prebuilt-read model (text/line/word/paragraph extraction with confidence scores, handwriting detection, optional searchable-PDF output), which this build will compare against Gemini on a real-paper sample. Older preview API versions (2023-10-31-preview through 2024-07-31-preview) lost support on 30 June 2026, and v3.0 GA (2022-08-31) is still supported but scheduled for end-of-support on 30 March 2029, so the build should target 2024-11-30 directly and avoid any preview version.

**Key findings**
- Current GA/stable API version is 2024-11-30 (v4.0), per Microsoft Learn overview and Read-model pages (ms.date 2026-09-08 / 2026-08-15, updated_at 2026-10-19) [docs opened directly].
- Python SDK package is azure-ai-documentintelligence; PyPI shows latest release 1.0.2, published 2025-03-27, supporting REST API version 2024-11-30 [opened PyPI page directly].
- Client class is DocumentIntelligenceClient (replacing the older azure-ai-formrecognizer DocumentAnalysisClient); core calls are begin_analyze_document(model_id, body) / begin_analyze_document_from_url(model_id, url), returning a poller whose .result() yields an AnalyzeResult with pages, paragraphs, lines, words, confidence, and styles (handwriting detection).
- Model ID for OCR is 'prebuilt-read'; it is the underlying OCR engine for all other prebuilt/custom models (layout, invoice, receipt, etc.).
- prebuilt-read in v4.0 supports PDF, JPEG/PNG/BMP/TIFF/HEIF images, and (new in v3.1+) Word/Excel/PowerPoint/HTML; for Office/HTML inputs there is NO angle/width/height/unit, NO bounding polygon/region, NO 'pages' query parameter support, and NO 'lines' object -- only words/paragraphs are returned for those formats.
- Input limits: paid (S0) tier allows up to 2,000 pages per PDF/TIFF and 500 MB file size; free (F0) tier processes only the first 2 pages and caps at 4 MB; image dimensions must be between 50x50 and 10,000x10,000 px; minimum extractable text height ~12 px at 1024x768 (~8pt at 150 DPI).
- F0 free tier gives 500 pages/month at no cost (confirmed on both the Read-model doc and the pricing page); exact S0 per-1,000-page $ pricing was not rendered on the public pricing page (JS-driven, region/program dependent) [uncertain].
- Searchable-PDF output (embedded-text PDF from a scanned PDF) is a v4.0 GA feature exclusive to prebuilt-read, requested via `?output=pdf` on the analyze call, at no added cost over the base GA Read price.
- End-of-support schedule as of Nov 2026: preview API versions (2023-10-31-preview, 2024-02-29-preview, 2024-07-31-preview) ended support 2026-06-30 (already past -- must not target these); REST v2.1 ends support 2027-09-15; REST v3.0 (2022-08-31) ends support 2029-03-30.
- Historical breaking change (pre-window but still load-bearing for anyone on old code): the 2023-07-31 REST release renamed `boundingBox` to `polygon` throughout analyze responses -- relevant only if migrating legacy v2.x/early v3.x code, not for new 2024-11-30 integrations.
- Docs are now served under the 'Foundry Tools' / Azure AI Foundry branding umbrella (ms.service: azure-document-intelligence-foundry-tools) as of the 2026 doc refresh, though the service, resource type (Microsoft.CognitiveServicesFormRecognizer), and SDK package names are unchanged.
- Resource provisioning is via Azure Portal 'Document Intelligence' (single-service) or the multi-service Azure AI Foundry resource create blade; keys/endpoint retrieved from the resource's Keys and Endpoint blade, same pattern as other Cognitive Services resources.

**Recommendations**
- Pin the SDK to azure-ai-documentintelligence>=1.0.2 and target REST api-version=2024-11-30 explicitly; do not use any *-preview api-version string.
- Use DocumentIntelligenceClient with DefaultAzureCredential (managed identity) in Azure Container Apps rather than a static API key, consistent with the repo's secrets-abstraction goal (no secrets in repo).
- For the OCR A/B gate, call begin_analyze_document('prebuilt-read', file_bytes) on the scanned-paper sample and compare extracted text/line confidence against the existing Gemini pipeline; prebuilt-layout can be kept as a fallback option if table/selection-mark structure in papers matters, but prebuilt-read is the right model for plain text OCR.
- If papers ever arrive as DOCX/PPTX/HTML (unlikely for scanned past papers but possible for source masters), be aware v4.0 drops bounding boxes/lines for those formats -- do not rely on polygon/line data for non-image/PDF inputs.
- Provision via the single-purpose 'Document Intelligence' Cognitive Services resource (not bundled multi-service) to keep IAM/cost scoping clean and simple to parameterize in Bicep without hardcoding region/project IDs.
- Get exact S0 per-page pricing from the Azure Pricing Calculator (region-specific, not shown on the public static page) before finalizing pricing.py cost-cap thresholds for the OCR gate.
- Do not attempt to resurrect any 2023/2024 preview API version for new work -- they are unsupported as of mid-2026; if any sample code found online still references a preview api-version, treat it as stale.

**current version:** API version 2024-11-30 (v4.0 GA); Python SDK azure-ai-documentintelligence 1.0.2

**api surface**
- pip install azure-ai-documentintelligence
- from azure.ai.documentintelligence import DocumentIntelligenceClient
- DocumentIntelligenceClient(endpoint, credential=AzureKeyCredential(key) or DefaultAzureCredential())
- client.begin_analyze_document('prebuilt-read', body=file_bytes).result()
- client.begin_analyze_document_from_url('prebuilt-read', url).result()
- result.pages[i].lines / .words (content, polygon, confidence)
- result.paragraphs[i].content
- result.styles[i].isHandwritten / confidence
- api-version query param: 2024-11-30
- optional output=pdf on analyze call for searchable-PDF retrieval

**pitfalls**
- Preview API versions (2023-10-31-preview, 2024-02-29-preview, 2024-07-31-preview) are already end-of-support as of 2026-06-30 -- do not target or copy sample code using these.
- v3.0 (2022-08-31) remains supported until 2029-03-30 but is not recommended for new development; v2.1 ends support 2027-09-15.
- For Office/HTML inputs on v4.0, prebuilt-read returns no bounding polygon/region, no page angle/width/height/unit, no 'pages' parameter support, and no 'lines' object -- only words/paragraphs.
- Old azure-ai-formrecognizer package and DocumentAnalysisClient are superseded by azure-ai-documentintelligence / DocumentIntelligenceClient; mixing the two SDKs in new code should be avoided.
- Custom models trained against a preview API version expire when that preview retires and must be retrained on the GA (2024-11-30) base model.
- Public pricing page does not render concrete per-page $ figures (dynamic/region-gated) -- actual S0 pricing must be pulled from the Azure Pricing Calculator for cost-cap config, not scraped from the static page.
- Historical (pre-window) breaking change for anyone referencing very old samples: 2023-07-31 REST release renamed `boundingBox` to `polygon` in all analyze responses.

*As of: Docs pages fetched carry ms.date 2026-08-15 / 2026-09-08 and updated_at 2026-10-19; PyPI package version 1.0.2 dated 2025-03-27. Current stable API version as of Nov 2026: 2024-11-30 (v4.0 GA).*

**Sources**
- [What Is Azure Document Intelligence in Foundry Tools? - Foundry Tools | Microsoft Learn](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/overview?view=doc-intel-4.0.0) (official-docs) -- "defaultMoniker: doc-intel-4.0.0 ... ms.date: 2026-09-08T00:00:00.0000000Z ... ms.service: azure-document-intelligence-foundry-tools"
- [Read model OCR data extraction - Document Intelligence - Foundry Tools | Microsoft Learn](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/prebuilt/read?view=doc-intel-4.0.0) (official-docs) -- "Document Intelligence v4.0: 2024-11-30 (GA) ... Model ID: prebuilt-read ... Searchable PDF is included with the 2024-11-30 GA prebuilt-read model with no added cost"
- [Migrate to v4.0. - Foundry Tools | Microsoft Learn (Document Intelligence migration guide)](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/versioning/migration-guide-overview) (official-docs) -- "Document Intelligence REST preview API versions (2024-07-31-preview, 2024-02-29-preview, 2023-10-31-preview) reach end of support on June 30, 2026 ... REST API 2022-08-31 v3.0 reaches end of support on March 30, 2029."
- [Use Document Intelligence client library or REST API - Foundry Tools | Microsoft Learn](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/how-to-guides/use-sdk-rest-api?view=doc-intel-4.0.0) (official-docs) -- "pip install azure-ai-documentintelligence ... client = DocumentIntelligenceClient(endpoint=endpoint, credential=AzureKeyCredential(key)) ... poller = client.begin_analyze_document("prebuilt-read", f)"
- [azure-ai-documentintelligence · PyPI](https://pypi.org/project/azure-ai-documentintelligence/) (official-docs) -- "Latest Version: 1.0.2 (released March 27, 2025) ... Supported API Version: 2024-11-30 ... DocumentIntelligenceClient ... begin_analyze_document()"
- [Azure AI Document Intelligence pricing](https://azure.microsoft.com/en-us/pricing/details/ai-document-intelligence/) (official-docs) -- "0 - 500 pages free per month ... 0-1M pages - $- per 1,000 pages"


### Official documentation: text-embedding-3-large
*Find the OFFICIAL documentation for "text-embedding-3-large": its current stable version, how it is installed or enabled, the API surface this build will use, and any breaking changes or pitfalls in the last 18 months, prioritising current state as of Nov 2026.*

text-embedding-3-large is OpenAI's current top-tier embedding model, default output 3072 dimensions, max input 8192 tokens, and natively supports a `dimensions` request parameter to shorten output (down to a minimum of 1) without needing a separate model, which is exactly how this build can produce 768-dim vectors for the existing Vector(768)/HNSW schema. It is available on both OpenAI's API and Azure OpenAI (via Microsoft Foundry) under the same `/embeddings` endpoint shape, with Azure's current docs (dated 2026-07-22) recommending Microsoft Entra ID auth over API keys and exposing it at `{endpoint}/openai/v1/embeddings`. No deprecation notice exists for this model as of Nov 2026; only legacy first-generation embedding models (pre-ada-002) were retired, back in January 2024.

**Key findings**
- text-embedding-3-large: default output 3072 dimensions, max input 8192 tokens per input, max 2048 inputs per array in one request, 300,000-token aggregate limit across all inputs in a single request (HTTP 400 if exceeded) — confirmed on both the OpenAI embeddings guide and the Azure OpenAI REST reference.
- The `dimensions` request parameter is officially documented as 'Only supported in text-embedding-3 and later models', min 1, no fixed minimum like 256 enforced by the API itself — confirmed on the Azure/Microsoft Foundry REST reference for the embeddings endpoint.
- A shortened text-embedding-3-large embedding at 256 dims was shown by OpenAI to outperform the unshortened text-embedding-ada-002 at 1536 dims on MTEB — from OpenAI's own embeddings guide, supporting that truncating to 768 dims for this build is a supported, sanctioned pattern, not a hack.
- Azure's current (2026-07-22-dated) how-to page uses the new unified `{endpoint}/openai/v1/embeddings` endpoint and recommends Microsoft Entra ID (DefaultAzureCredential / managed identity) authentication over long-lived API keys; API-key auth is still supported but secondary in the docs.
- On Azure, the request body's `model` field is the deployment name, not necessarily the underlying model id — relevant for mapping config in a provider-neutral seam.
- No deprecation entry exists for text-embedding-3-large, text-embedding-3-small, or text-embedding-ada-002 as of the current OpenAI deprecations page; only first-generation (pre-ada-002) embedding models were shut down, on 2024-01-04, well outside the 18-month research window.
- Azure AI Foundry model catalog lists the model's context window as 8191 tokens (effectively the same 8192-token limit, off-by-one in labeling) and confirms it is hosted on Azure with pay-as-you-go or reserved PTU options [uncertain] (deployment-type/region detail was truncated on the catalog page).

**Recommendations**
- Explicitly pass `dimensions=768` on every embed call (OpenAI and Azure OpenAI alike) rather than relying on the 3072 default, to satisfy the Vector(768)/HNSW schema requirement and stay well under pgvector's 2000-dim HNSW cap.
- In the provider-neutral embedding seam, keep a separate config field for the Azure deployment name vs. the model id string, since Azure's `model` request field is the deployment name.
- Prefer Microsoft Entra ID / managed identity for Azure OpenAI auth in the secrets/config seam over a stored API key, matching current Microsoft guidance and the 'no secrets in repo' constraint.
- When scripting the re-embed/backfill job, chunk batches to respect the 2048-inputs-per-array and 300,000-aggregate-token-per-request limits (per-paper-chunk batches should be well under this, but verify at scale).
- Before approving the OCR/embedding re-ingest, confirm text-embedding-3-large is actually deployed and available in the chosen Azure region/resource — region availability is not consolidated in one static table and should be checked directly in the target Azure AI Foundry resource at deploy time [uncertain].
- Treat exact per-token pricing as a value to re-verify against the live OpenAI/Azure pricing pages when writing pricing.py, rather than trusting any single cached snapshot.

**current version:** text-embedding-3-large (OpenAI embedding models are not versioned with semantic version numbers; this is the current, non-deprecated top-tier embedding model as of Nov 2026, default output 3072 dimensions)

**api surface**
- POST https://api.openai.com/v1/embeddings (OpenAI direct) or POST {endpoint}/openai/v1/embeddings?api-version=v1 (Azure OpenAI) — body: {model, input, dimensions, encoding_format}
- Request field `dimensions` (integer, min 1) — set to 768 to match this build's Vector(768) column
- Request field `encoding_format` — 'float' (default) or 'base64'
- Request field `input` — string, array of strings, or token arrays; max 8192 tokens per input, max 2048 inputs per array, 300,000-token aggregate cap per request
- Azure auth: Microsoft Entra ID via DefaultAzureCredential/managed identity (recommended) or API key in `api-key`/`authorization` header

**pitfalls**
- Default output is 3072 dimensions, not 768 — every call must explicitly pass `dimensions=768` or the stored vectors will not fit the existing Vector(768)/HNSW schema.
- Azure enforces a 300,000-token aggregate limit summed across all inputs in a single request (separate from the 8192-token per-input cap) — batch the re-embed job accordingly.
- Max 2048 inputs per array per request on both OpenAI and Azure — relevant for bulk backfill scripting.
- On Azure, the `model` field in the request body is the deployment name, which can differ from the underlying model id — a provider-neutral seam must map these separately.
- Azure's current docs push the newer unified `/openai/v1/embeddings` endpoint and Entra ID auth; older Azure examples used `/openai/deployments/{deployment-id}/embeddings?api-version=...` with API keys — confirm which surface the SDK/pin in use actually targets to avoid mixing API shapes.
- Region/deployment-type availability for text-embedding-3-large on Azure was not confirmed from a single authoritative table in this research — verify directly against the target Azure resource before scripting deployment [uncertain].

*As of: Nov 2026 snapshot; Azure OpenAI 'Generate embeddings' how-to page dated 2026-07-22, Azure/Microsoft Foundry embeddings REST reference dated 2026-05-27 (updated 2026-07-09), OpenAI embeddings guide and deprecations page undated but reflect current live state as fetched*

**Sources**
- [OpenAI API docs — Embeddings guide](https://developers.openai.com/api/docs/guides/embeddings) (official-docs) -- "Both of our new embedding models were trained with a technique that allows developers to trade-off performance and cost... a shortened text-embedding-3-large embedding can outperform an unshortened text-embedding-ada-002 embedding"
- [OpenAI API docs — text-embedding-3-large model page](https://developers.openai.com/api/docs/models/text-embedding-3-large) (official-docs) -- "our most capable embedding model for both english and non-english tasks ... supports the embeddings endpoint (v1/embeddings) and batch processing"
- [OpenAI API docs — Deprecations](https://developers.openai.com/api/docs/deprecations) (official-docs) -- "we announced the upcoming retirement of our first-generation text embedding models. They will be shut down on January 04, 2024."
- [Generate embeddings with Azure OpenAI - Microsoft Foundry | Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/embeddings) (official-docs) -- "The v1 embeddings API supports Microsoft Entra ID and API key authentication. Microsoft Entra ID is recommended because it avoids storing long-lived credentials."
- [Microsoft Foundry REST Reference - Azure OpenAI - Embeddings](https://learn.microsoft.com/en-us/rest/api/microsoft-foundry/azureopenai/embeddings) (official-docs) -- "dimensions | integer | The number of dimensions the resulting output embeddings should have. Only supported in text-embedding-3 and later models. Constraints: min: 1"
- [Azure AI Foundry model catalog — text-embedding-3-large](https://ai.azure.com/catalog/models/text-embedding-3-large) (official-docs) -- "8191 [listed as context window in technical specs]"


### Official documentation: Azure Database for PostgreSQL Flexible Server
*Find the OFFICIAL documentation for "Azure Database for PostgreSQL Flexible Server": its current stable version, how it is installed or enabled, the API surface this build will use, and any breaking changes or pitfalls in the last 18 months, prioritising current state as of Nov 2026.*

Azure Database for PostgreSQL Flexible Server is the target managed Postgres; it currently defaults new servers to PostgreSQL 18 (minor 18.6), with 17.11/16.15/15.19/14.24 also GA and 13/12/11 in extended support (docs dated 2026-08-26). pgvector ('vector' extension, v0.8.2 confirmed on PG16) and pg_trgm are both allowlisted extensions enabled via the azure.extensions server parameter then CREATE EXTENSION. HNSW indexing is supported with the documented 2000-dimension cap, which the build's 768-dim embeddings satisfy with headroom; IVFFlat and DiskANN are also available. The az CLI 'postgres flexible-server' command group had several 2025-2026 breaking changes (removed --create-default-database/--database-name, PG12 support removed then later extended, networking args removed) that matter for the Bicep/CLI-based provisioning script.

**Key findings**
- docs.ms (2026-08-26): supported major versions are PG18 (minor 18.6, default for new servers), 17 (17.11), 16 (16.15), 15 (15.19), 14 (14.24); PG13/12/11 in Extended Support only.
- docs.ms (2026-07-10): extension binary/name is 'vector' (not 'pgvector'); must be added to the azure.extensions allowlist server parameter before CREATE EXTENSION vector; pg_trgm is also allowlisted, no shared_preload_libraries needed.
- docs.ms (2026-07-10): HNSW index limit confirmed verbatim: 'You can only index a column that has up to 2000 dimensions' — error otherwise; 768-dim embeddings are well within this cap.
- docs.ms (2026-07-10): HNSW create syntax is `CREATE INDEX ... USING hnsw (col vector_l2_ops) WITH (m = 16, ef_construction = 64);` with query-time tuning via `SET hnsw.ef_search = 100;` (defaults m=16, ef_construction=64, ef_search=40).
- docs.ms CLI release notes (2026-07-08 page, covering through v2.88.0): breaking changes in 2025-2026 include removal of --create-default-database/--database-name (v2.81.0, Dec 2025), default --create-default-database set to Disabled then later removed, removal of PG12 support (v2.73.0, May 2025) followed by an extension of PG11/12 EOL support (v2.75.0, Jul 2025), and removal of networking args --address-prefixes/--subnet-prefixes plus stopped auto-creation of network resources on create/restore/replica (v2.87.0, Jun 2026).
- docs.ms REST API release notes (2026-10-29): current stable GA API version is 2026-10-01; it removes the PostgreSQL version enum constraint so new major versions (e.g., PG19 preview) don't require an API schema bump.
- docs.ms (2026-07-10): extension page recommends `vector_ip_ops`/<#> for inner-product search when embeddings are normalized (e.g., OpenAI-style embeddings), relevant to the build's 768-dim vectors.
- techcommunity blog title found ('What's new with Postgres at Microsoft, 2026 edition') but body could not be retrieved via fetch tool, so Premium SSDv2/new-region claims from that search snippet are not independently confirmed.

**Recommendations**
- Provision Flexible Server targeting PG16 or PG17 (not forcing PG18) unless all required extensions/features are confirmed compatible with PG18's listed extension limitations.
- Allowlist both 'vector' and 'pg_trgm' via `az postgres flexible-server parameter set --name azure.extensions --value "vector,pg_trgm"` (or Bicep parameter) before any CREATE EXTENSION step, in both Bicep template and migration script.
- Keep embeddings at 768 dims and use HNSW (not IVFFlat) for the production index per criteria #6; this is safely under the 2000-dim HNSW cap with large margin.
- In Bicep/CLI scripts for server create/restore, do not rely on --create-default-database, --database-name, --address-prefixes, or --subnet-prefixes; use the separate `az postgres flexible-server db create` command group and pre-existing subnet instead, since these were removed/changed in 2025-2026 CLI releases.
- Target REST API version 2026-10-01 (or pin an explicit GA version) in Bicep/ARM templates rather than an unversioned/preview API, to avoid picking up preview-only behavior.
- Treat the techcommunity 'What's new 2026' blog claims as unverified; re-fetch or find an alternate source if those specifics (SSDv2 64TB, new regions) become load-bearing for the Bicep plan.

**current version:** PostgreSQL 18 (minor 18.6) is the default for new Flexible Server instances; 17.11, 16.15, 15.19, 14.24 are also GA minors; REST API stable GA version is 2026-10-01; pgvector ('vector') extension is at v0.8.2 on PG16.

**api surface**
- CREATE EXTENSION vector; / CREATE EXTENSION pg_trgm; (after allowlisting via azure.extensions server parameter)
- az postgres flexible-server parameter set --name azure.extensions --value "vector,pg_trgm"
- CREATE INDEX ... USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64); SET hnsw.ef_search = 100;
- <=> (cosine), <-> (L2), <#> (negative inner product) operators for ORDER BY ... LIMIT k queries
- az postgres flexible-server create/db create/firewall-rule create (CLI) and Microsoft.DBforPostgreSQL/flexibleServers Bicep resource type, REST API version 2026-10-01
- Standard SQLAlchemy 2.0 + psycopg connection string against the Flexible Server host/port/db (no proprietary driver needed)

**pitfalls**
- HNSW/IVFFlat indexing hard-caps at 2000 dimensions per column; exceeding it throws 'column cannot have more than 2000 dimensions for INDEX_TYPE index' — not a concern at 768 dims but must not be raised later without re-architecting.
- az CLI v2.81.0 (Dec 2025) removed --create-default-database and --database-name from `flexible-server create`; migration/provisioning scripts must use `az postgres flexible-server db create` instead.
- az CLI v2.73.0 (May 2025) removed PG12 support and changed default --create-default-database to Disabled, then v2.75.0 (Jul 2025) extended EOL support for PG11/12 again — version-pinning logic in scripts should not assume a fixed default PG version across CLI releases.
- az CLI v2.87.0 (Jun 2026) stopped flexible-server create/restore/replica-create/revive-dropped from creating or altering networking components and removed --address-prefixes/--subnet-prefixes — Bicep/CLI provisioning must pre-create the subnet/VNet separately.
- The pgvector extension's own name is 'vector', not 'pgvector' — using the wrong name in allowlist or CREATE EXTENSION commands will fail silently with a not-found error.
- Techcommunity 'What's new 2026' blog content (Premium SSDv2 64TB, new regions, Grafana dashboards) could not be opened/verified in this session; treat those specific claims as unconfirmed until re-checked.

*As of: Primary docs dated 2026-08-26 (supported versions) and 2026-07-10 (pgvector/extensions pages); CLI release notes page dated 2026-07-08 covering releases through v2.88.0 (2026-07-07); REST API release notes page dated 2026-10-29 covering API version 2026-10-01.*

**Sources**
- [Supported versions of PostgreSQL in Azure Database for PostgreSQL flexible server](https://learn.microsoft.com/en-us/azure/postgresql/configure-maintain/concepts-supported-versions) (official-docs) -- "Azure Database for PostgreSQL currently supports the following major versions... PostgreSQL version 18. The current minor release is 18.6."
- [Vector Search in Azure Database for PostgreSQL Flexible Server](https://learn.microsoft.com/en-us/azure/postgresql/extensions/how-to-use-pgvector) (official-docs) -- "the name of the binary and the extension itself is simply `vector`... running the CREATE EXTENSION command."
- [Optimize Performance when Using pgvector in Azure Database for PostgreSQL Flexible Server](https://learn.microsoft.com/en-us/azure/postgresql/extensions/how-to-optimize-performance-pgvector) (official-docs) -- "You can only index a column that has up to 2000 dimensions. Attempting to index a column with more dimensions results in the error..."
- [Allow Extensions in Azure Database for PostgreSQL Flexible Server](https://learn.microsoft.com/en-us/azure/postgresql/extensions/how-to-allow-extensions) (official-docs) -- "az postgres flexible-server parameter set ... --name azure.extensions --value "<extension_name>,<extension_name>""
- [Supported extensions versions in Azure Database for PostgreSQL - Flexible Server (by engine)](https://learn.microsoft.com/en-us/azure/postgresql/extensions/concepts-extensions-by-engine?pivots=postgresql-16) (official-docs) -- "pg_trgm Version 1.6 ... vector Version 0.8.2 ... Vector data type and ivfflat and hnsw access methods."
- [Release notes for the CLI module for Azure Database for PostgreSQL flexible server](https://learn.microsoft.com/en-us/azure/postgresql/release-notes/release-notes-cli) (official-docs) -- "[BREAKING CHANGE] Remove default value for `--version`, and remove `--create-default-database` and `--database-name`."
- [Release notes for the REST APIs for Azure Database for PostgreSQL flexible server](https://learn.microsoft.com/en-us/azure/postgresql/release-notes/release-notes-api) (official-docs) -- "2026-10-01 | Stable (GA) ... Removes the PostgreSQL version enumeration constraint..."


### Official documentation: pgvector
*Find the OFFICIAL documentation for "pgvector": its current stable version, how it is installed or enabled, the API surface this build will use, and any breaking changes or pitfalls in the last 18 months, prioritising current state as of Nov 2026.*

pgvector's official docs (GitHub README/CHANGELOG, Azure Database for PostgreSQL docs) confirm the extension is installed via CREATE EXTENSION vector (after allowlisting it as 'vector', not 'pgvector', on Azure Flexible Server), and that vector(768) with an HNSW index on vector_cosine_ops is well within limits since HNSW/vector type supports up to 2000 dimensions. Current stable is v0.8.7 (2026-10-01); a run of 0.8.x patches through 2026 fixed real buffer-overflow and HNSW index-corruption/vacuuming bugs, so the build should pin to >=0.8.4 (ideally 0.8.7), not an older 0.7.x/early 0.8.x build. An unreleased 0.9.0 (targeted late Nov/early Dec 2026) will drop Postgres 13/14 support, which is a future-compat watch item but not yet shipped.

**Key findings**
- Current stable release: v0.8.7, tagged 2026-10-01 per the pgvector GitHub tags page.
- Install: compile from source (git clone --branch v0.8.7, make && make install) or via Docker/Homebrew/APT/Yum/pkg/APK/conda-forge per the README; on Azure it's a managed extension, not compiled by the user.
- Enable on Azure Database for PostgreSQL Flexible Server: binary/extension name is literally 'vector' (not 'pgvector') -- must be added to the azure.extensions allowlist, then `CREATE EXTENSION vector;` per database (Microsoft Learn, ms.date 2026-07-10, updated 2026-07-13).
- Dimension limits per type (README): vector up to 2,000 dims, halfvec up to 4,000, bit up to 64,000, sparsevec up to 1,000 non-zero elements -- vector(768) with HNSW is well inside the 2000-dim cap this build already relies on.
- HNSW index syntax: CREATE INDEX ON items USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64); defaults m=16, ef_construction=64; search-time recall/speed tradeoff via SET hnsw.ef_search = <n> (default 40), settable per-session or SET LOCAL per-transaction.
- Distance operators: <-> (L2), <#> (negative inner product), <=> (cosine), <+> (L1), plus <~> (Hamming) and <%> (Jaccard) for bit vectors; functions include cosine_distance(), l2_distance(), l1_distance(), inner_product(), vector_dims(), vector_norms(), and AVG/SUM aggregates.
- 0.7.0 (2024-04-29) added halfvec and sparsevec types, L1 distance with HNSW, binary quantization, Hamming/Jaccard distance, and CPU dispatching for Linux x86-64 -- all predate this build's needs but show the extension actively evolved in the research window.
- 0.8.0 (2024-10-30) added iterative index scans for filtered queries and dropped PostgreSQL 12 support.
- 0.8.1 (2025-09-04) added PostgreSQL 18 rc1 support.
- Security/stability fixes in 2026: 0.8.2 (2026-02-25) fixed a buffer overflow with parallel HNSW index build; 0.8.3 (2026-06-17) fixed possible index corruption with HNSW vacuuming; 0.8.4 (2026-06-30) fixed an 'hnsw graph not repaired' error and a possible error with inserts during HNSW vacuuming; 0.8.6/0.8.7 fixed further buffer overflows (primarily IVFFlat index build, including a 32-bit-specific case).
- Maintenance note from the README: HNSW vacuuming can be slow; consider REINDEX INDEX CONCURRENTLY before VACUUM on large HNSW indexes.
- pgvector 0.9.0 is unreleased as of Nov 2026: GitHub issue #1042 (open, targeted late Nov/early Dec 2026) plans async I/O for HNSW and explicitly plans to drop Postgres 13 and 14 support. [uncertain]

**Recommendations**
- Target pgvector >=0.8.4 at minimum (fixes the HNSW vacuuming index-corruption bug); prefer the current 0.8.7 if/when Azure Flexible Server's managed extension catalog offers it, since it also carries later buffer-overflow fixes.
- On Azure Database for PostgreSQL Flexible Server, remember the extension must be allowlisted and created as `vector`, not `pgvector` -- update Bicep/provisioning scripts and docs to use `azure.extensions` plus `CREATE EXTENSION vector;`, matching acceptance criterion 6 (Vector(768) column unchanged).
- Keep HNSW index definition as `USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)` (or whatever the existing defaults are) since vector(768) is far under the 2000-dim cap -- no index-type change is needed for the Azure move.
- Before running destructive vacuum/reindex operations on the HNSW index during the re-embed step, check the deployed pgvector version; if it predates 0.8.4, schedule REINDEX INDEX CONCURRENTLY before VACUUM to avoid known corruption/slowness issues.
- Do not plan around pgvector 0.9.0 features (async I/O for HNSW) yet -- it is unreleased and will drop Postgres 13/14 support, which should be checked against the target Flexible Server Postgres version before any future upgrade.

**current version:** v0.8.7 (released 2026-10-01)

**api surface**
- CREATE EXTENSION vector; (Azure: must first allowlist via azure.extensions)
- column type: vector(768)
- CREATE INDEX ... USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)
- operator <=> for cosine distance in ORDER BY for top-k retrieval
- SET hnsw.ef_search = <n>; / SET LOCAL hnsw.ef_search = <n>; for recall/speed tuning
- functions: cosine_distance(vector, vector), vector_dims(vector), l2_distance(vector, vector)

**pitfalls**
- Azure Flexible Server requires the extension to be allowlisted and created under the name `vector`, not `pgvector` -- a common provisioning mistake.
- pgvector 0.8.2 and earlier in this window had a buffer overflow with parallel HNSW index build (fixed 0.8.2); 0.8.3 fixed possible HNSW index corruption during vacuuming; pin to >=0.8.4 to avoid both.
- HNSW vacuuming can be slow on large indexes; the README recommends REINDEX INDEX CONCURRENTLY before VACUUM.
- pgvector 0.8.0 (2024-10-30) dropped PostgreSQL 12 support; the still-unreleased 0.9.0 plans to drop Postgres 13 and 14 -- check target Flexible Server's Postgres major version against future pgvector upgrades. [uncertain]
- vector type HNSW/IVFFlat dimension cap is 2,000 -- confirms embeddings must stay at 768 per this build's constraint, but leaves no room to naively switch to a much higher-dimension embedding model later without moving to halfvec (4,000-dim cap) or reducing dims.

*As of: 2026-11 (pgvector v0.8.7, released 2026-10-01; Azure pgvector doc updated 2026-07-13)*

**Sources**
- [pgvector/pgvector (GitHub README)](https://github.com/pgvector/pgvector) (official-docs) -- "Supported types are: vector - up to 2,000 dimensions ... CREATE INDEX ON items USING hnsw (embedding vector_cosine_ops);"
- [pgvector CHANGELOG.md](https://raw.githubusercontent.com/pgvector/pgvector/master/CHANGELOG.md) (official-docs) -- "0.8.3 (2026-06-17) - Fixed possible index corruption with HNSW vacuuming"
- [pgvector tags](https://github.com/pgvector/pgvector/tags) (repo) -- "v0.8.7 - October 1, 2026"
- [0.9.0 Plan · Issue #1042 · pgvector/pgvector](https://github.com/pgvector/pgvector/issues/1042) (repo) -- "drop support for Postgres 13 and 14 ... async I/O for HNSW ... targets late November or early December"
- [Vector Search in Azure Database for PostgreSQL Flexible Server - Microsoft Learn](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/how-to-use-pgvector) (official-docs) -- "Although the PostgreSQL community refers to this extension as pgvector, the name of the binary and the extension itself is simply `vector`. ... CREATE EXTENSION vector;"


### Official documentation: pg_trgm
*Find the OFFICIAL documentation for "pg_trgm": its current stable version, how it is installed or enabled, the API surface this build will use, and any breaking changes or pitfalls in the last 18 months, prioritising current state as of Nov 2026.*

pg_trgm is a core PostgreSQL contrib extension (not a separate product) providing trigram-based text similarity and fast GiST/GIN index searching; its current bundled module version is 1.6 (unchanged since PostgreSQL 14) and it is installed with `CREATE EXTENSION pg_trgm;`. This build will use its `%` similarity operator and `gin_trgm_ops`/`gist_trgm_ops` operator classes alongside pgvector HNSW, and on the target platform (Azure Database for PostgreSQL Flexible Server) it must additionally be allow-listed via the `azure.extensions` server parameter before `CREATE EXTENSION` will succeed. The main recent pitfall is PostgreSQL 18 (Sep 2025): a non-libc-collation behavior change affecting pg_trgm (recommend reindex after major upgrade) and a since-patched CVE-2026-2007 buffer overrun in pg_trgm's lowercasing, fixed in 18.2 (Feb 2026) — both are PG18-only issues.

**Key findings**
- Official docs confirm: `CREATE EXTENSION pg_trgm;` — trusted extension, installable by non-superuser with CREATE privilege on the database.
- Core functions: similarity(text,text)->real, show_trgm(text)->text[], word_similarity(text,text)->real, strict_word_similarity(text,text)->real.
- Operators: `%` (similarity > pg_trgm.similarity_threshold, default 0.3), `<->` (distance), `<%`/`%>` (word similarity, default threshold 0.6), `<<%`/`%>>` (strict word similarity, default threshold 0.5), plus matching distance operators.
- Index support: GIN (`gin_trgm_ops`) and GiST (`gist_trgm_ops`, optional siglen 1–2024) operator classes; both accelerate `%`, LIKE/ILIKE, and regex (~, ~*) queries; GiST additionally supports efficient nearest-neighbor ordering via `<->`.
- Azure Database for PostgreSQL Flexible Server extension matrix (Microsoft Learn, updated 2026-07-10): pg_trgm module version 1.6 on PG14–18, 1.5 on PG13, 1.4 on PG11–12 — no shared_preload_libraries needed.
- Azure-specific pitfall [uncertain, forum-sourced]: pg_trgm can be rejected with "extension 'pg_trgm' is not allow-listed" until the server parameter `azure.extensions` includes `pg_trgm`, set before running `CREATE EXTENSION IF NOT EXISTS pg_trgm;`.
- PostgreSQL 18.0 (2025-09-25) release notes: full-text search/pg_trgm now use the cluster's default collation provider instead of always libc; clusters on non-libc providers (ICU/builtin) may see behavior changes and should reindex pg_trgm-related indexes after pg_upgrade.
- PostgreSQL 18.2 (2026-02-12) fixed CVE-2026-2007: a pg_trgm buffer overrun from locale-dependent lowercasing producing more characters than the input — bug was introduced in v18, so only affects 18.0/18.1.

**Recommendations**
- Install with the standard `CREATE EXTENSION IF NOT EXISTS pg_trgm;` in the migration/Bicep provisioning script, same as GCP.
- On Azure Flexible Server, add `pg_trgm` to the `azure.extensions` allow-list server parameter (via Bicep/CLI) before the extension-create step runs, or CREATE EXTENSION will fail.
- Use `gin_trgm_ops` (not GiST) for the trigram index backing fuzzy/typo-tolerant text search alongside the Vector(768) HNSW column, since GIN is the better fit for simple similarity/LIKE matching at this scale and keeps writes cheaper than GiST signatures.
- If targeting PostgreSQL 18 specifically, pin to 18.2+ (or current patch) to pick up the CVE-2026-2007 fix; this is moot if Azure provisions PG14–17.
- If the target server uses a non-libc collation provider (ICU/builtin) and is later major-upgraded, plan to reindex all pg_trgm indexes post-upgrade per the PG18 migration notes — not an immediate concern for a fresh Azure deployment but relevant for any future PG18 jump.
- Do not assume default-provider parity with the old GCP Cloud SQL instance; verify the Azure Flexible Server's collation provider matches expectations before re-embedding/re-indexing to avoid silent trigram-matching drift.

**current version:** pg_trgm module version 1.6 (bundled in PostgreSQL core contrib for PG 14–18; no independently versioned release outside PostgreSQL itself)

**api surface**
- CREATE EXTENSION IF NOT EXISTS pg_trgm;
- similarity(text, text) -> real
- % operator (similarity threshold match, controlled by pg_trgm.similarity_threshold)
- CREATE INDEX ... USING GIN (column gin_trgm_ops);
- CREATE INDEX ... USING GIST (column gist_trgm_ops);
- SET pg_trgm.similarity_threshold = 0.3; (and word_similarity_threshold / strict_word_similarity_threshold if word-boundary matching is used)
- LIKE/ILIKE and ~ / ~* pattern queries accelerated by the trigram index

**pitfalls**
- PG18-only: full-text search/pg_trgm collation-provider change can alter trigram extraction on non-libc (ICU/builtin) clusters; reindex pg_trgm indexes after pg_upgrade to PG18.
- PG18.0/18.1-only: CVE-2026-2007 buffer overrun in pg_trgm lowercasing logic, fixed in 18.2 (2026-02-12) — ensure provisioned version is 18.2+ if PG18 is used.
- Azure Flexible Server requires pg_trgm to be added to the `azure.extensions` allow-list server parameter before CREATE EXTENSION will succeed [uncertain: sourced from a Microsoft Q&A forum post, not the official extensions page itself, though consistent with documented allow-list mechanism].
- Trigram indexes degrade to full-index scans for patterns with no extractable trigrams (e.g., very short search terms) — relevant if query-set strings in the top-k parity test are short.

*As of: 2026-11 (PostgreSQL docs 'current' = v18 branch incl. 18.6 released 2026-08-13; Azure extensions page dated 2026-07-10)*

**Sources**
- [PostgreSQL: Documentation: current: F.35. pg_trgm](https://www.postgresql.org/docs/current/pgtrgm.html) (official-docs) -- "The pg_trgm module provides functions and operators for determining the similarity of alphanumeric text based on trigram matching, as well as index operator classes that support fast searching for similar strings."
- [PostgreSQL 18.0 Release Notes](https://www.postgresql.org/docs/release/18.0/) (official-docs) -- "Change full text search to use the default collation provider of the cluster to read configuration files and dictionaries, rather than always using libc ... as well as the pg_trgm extension. When upgrading such clusters using pg_upgrade, it is recommended to reindex all indexes related to full-text search and pg_trgm after the upgrade."
- [PostgreSQL 18.2 Release Notes](https://www.postgresql.org/docs/release/18.2/) (official-docs) -- "Harden contrib/pg_trgm against changes in string lowercasing behavior ... Fix potential buffer overruns arising from the fact that in some locales lower-casing a string can produce more characters ... That behavior is new in version 18, and so is the bug. (CVE-2026-2007)"
- [List of Extensions and Modules by Name in Azure Database for PostgreSQL Flexible Server](https://learn.microsoft.com/en-us/azure/postgresql/extensions/concepts-extensions-versions) (official-docs) -- "pg_trgm provides text similarity measurement and index searching based on trigrams. | PostgreSQL version 18/17/16/15/14 | 1.6 | 13 | 1.5 | 12/11 | 1.4"
- [pg_trgm Extension Not Allowed on Azure Database for PostgreSQL Flexible Server](https://learn.microsoft.com/en-us/answers/questions/5537068/pg-trgm-extension-not-allowed-on-azure-database-fo) (forum) -- "ERROR: extension 'pg_trgm' is not allow-listed for users in Azure Database for PostgreSQL ... add pg_trgm to the azure.extensions server parameter."


### Official documentation: Azure Container Apps Jobs
*Find the OFFICIAL documentation for "Azure Container Apps Jobs": its current stable version, how it is installed or enabled, the API surface this build will use, and any breaking changes or pitfalls in the last 18 months, prioritising current state as of Nov 2026.*

Azure Container Apps Jobs is a GA feature of Azure Container Apps for running finite-duration containerized tasks (Manual, Schedule, or Event trigger types), which fits this build's ingest and backfill workloads exactly as the PRD specifies (AC #8). It is created/managed via `az containerapp job` CLI commands (requiring the `containerapp` CLI extension), Bicep/ARM resource type `Microsoft.App/jobs`, or the REST API, and shares the same Container Apps Environment as the bot/review apps for networking and logging. The core API surface (trigger types, replica settings, start/execution-list operations) has been stable, but a permission tightening for job-start overrides is actively rolling out as of Nov 2026, and there's a known API-version registration gap (2026-07-01) that can break job start calls from newer SDKs — both are directly relevant to this build's scripted-but-not-yet-executed ingest/backfill jobs.

**Key findings**
- Container Apps Jobs supports three trigger types: Manual (on-demand via CLI/portal/ARM), Schedule (cron, evaluated in UTC), and Event (KEDA-based custom scalers) — per https://learn.microsoft.com/en-us/azure/container-apps/jobs (ms.date 2026-09-16).
- Jobs do NOT support Dapr or ingress/custom domains/SSL — confirmed restriction on the same official page, relevant since ingest/backfill jobs must not rely on inbound HTTP.
- Job execution history via `az containerapp job execution list` / REST GET .../jobs/{name}/executions is limited to the most recent 100 successful and 100 failed executions; full audit requires querying the environment's configured log sink.
- Platform maintenance can interrupt long-running replicas; official docs recommend replicaRetryLimit >= 1 and at-least-once-safe workload design — directly applicable to multi-hour OCR/embedding backfill jobs.
- As of 2026-11-02, Microsoft is actively rolling out (fully active across all production regions within ~2 weeks of that date) a permission change: starting a job with any container/init-container execution override (including an empty array) now requires BOTH `Microsoft.App/jobs/start/action` AND `Microsoft.App/jobs/write`; failures surface as HTTP 400 `JobStartOverrideAuthorizationFailed` — source: https://github.com/microsoft/azure-container-apps/issues/1872.
- Both built-in roles 'Container Apps Jobs Contributor' and 'Container Apps Jobs Operator' include a `Microsoft.App/jobs/*/action` wildcard that also matches `listSecrets`, so anyone who can start a job can read that job's secrets in plaintext — confirmed on the same official jobs doc page.
- azure-mgmt-appcontainers Python SDK 5.1.0 defaults to API version 2026-07-01 for Container Apps Jobs, which was reported not yet registered for Microsoft.App/jobs in all regions, breaking job-start calls — source: https://github.com/Azure/azure-sdk-for-python/issues/49044 [uncertain: whether this is fully resolved as of Nov 2026].
- The `az containerapp job create` command (manual example) uses parameters: --name, --resource-group, --environment, --trigger-type, --replica-timeout, --replica-retry-limit, --replica-completion-count, --parallelism, --image, --cpu, --memory, plus --cron-expression (Schedule) or --min-executions/--max-executions/--scale-rule-* (Event) — confirmed on the official jobs doc page.
- The containerapp CLI functionality ships as an Azure CLI extension (`az extension add --name containerapp --upgrade`, requires CLI >= 2.79.0 per a surfaced AI summary of search results); since May 2024 extensions no longer enable preview features by default, requiring `--allow-preview true` for preview-only features [uncertain — not opened directly, derived from search summary, not a fetched official page].

**Recommendations**
- Define the ingest and backfill Container Apps Jobs with triggerType Manual in Bicep (Microsoft.App/jobs), started explicitly by the owner-approved cutover/migration script — never Schedule, to preserve the 'not executed until sign-off' requirement.
- Set replicaRetryLimit >= 1 and a generous replicaTimeout for the OCR/embedding backfill job, and design the ingest/backfill logic to be idempotent (at-least-once), per the platform-maintenance-interruption note in the official docs.
- When the scripted migration runbook (AC #9) triggers job executions, avoid passing container/init-container override templates if possible; if overrides are required (e.g., per-batch parameters), ensure the identity running the script holds both `Microsoft.App/jobs/start/action` and `Microsoft.App/jobs/write` to avoid the Nov 2026 permission-change breakage.
- Pin an explicit, tested apiVersion (not 'latest') on the Bicep Microsoft.App/jobs resource — avoid 2026-07-01 given the reported regional-registration gap; verify the chosen version is registered in the target region before relying on it in the Bicep deploy for AC #8.
- Scope RBAC narrowly: grant 'Container Apps Jobs Contributor' only to the deploy pipeline identity and 'Container Apps Jobs Operator' only to the identity/person approving manual starts; do not create custom roles with `Microsoft.App/jobs/*/action` wildcards, since that implicitly grants secret read access.
- Confirm CI/build agents have the `containerapp` Azure CLI extension installed/upgraded (`az extension add --name containerapp --upgrade`) before any `az containerapp job` command runs in the Bicep/CLI deployment scripts.
- Do not attempt to expose the ingest/backfill job as an HTTP-reachable service (Dapr/ingress) — use the bot/review Container Apps for anything requiring inbound traffic, per the stated jobs restrictions.

**current version:** GA platform feature (no separate version number); ARM resource type Microsoft.App/jobs — official doc examples use api-version 2023-05-01, while SDKs/tooling were observed defaulting to 2026-01-01/2026-07-01 in late 2026 [uncertain]

**api surface**
- az containerapp job create|update|delete|list|show|start|stop
- az containerapp job execution list
- Bicep/ARM resource Microsoft.App/jobs: properties.configuration.triggerType (Manual|Schedule|Event), manualTriggerConfig, scheduleTriggerConfig (cronExpression), eventTriggerConfig (scale rules), replicaTimeout, replicaRetryLimit, parallelism, replicaCompletionCount
- REST: POST /subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.App/jobs/{name}/start, GET .../jobs/{name}/executions
- RBAC roles: Container Apps Jobs Contributor, Container Apps Jobs Operator, Monitoring Reader (optional)
- containerapp Azure CLI extension (required for all az containerapp job commands) [uncertain on exact min version]

**pitfalls**
- Nov 2026 rollout: job-start calls with container/init-container overrides (including empty arrays) now need Microsoft.App/jobs/write in addition to start/action, or they fail with JobStartOverrideAuthorizationFailed — audit any CI/migration scripts that start jobs with overrides.
- azure-mgmt-appcontainers 5.1.0 defaulted to API version 2026-07-01, which was reported not registered for Microsoft.App/jobs in all regions, breaking job starts — pin a known-good apiVersion in Bicep rather than 'latest'.
- Job execution history caps at the most recent 100 successful + 100 failed executions; rely on the environment's log sink for durable backfill/ingest run history.
- Container Apps Jobs do not support Dapr or ingress/custom domains/SSL — do not architect ingest/backfill jobs to serve HTTP.
- Jobs Contributor/Operator built-in roles both carry a Microsoft.App/jobs/*/action wildcard that also matches listSecrets, so anyone able to start a job can read its secrets in plaintext — avoid wildcard custom roles for least-privilege automation identities.
- Long-running job replicas can be interrupted by routine platform maintenance; set replicaRetryLimit >= 1 and ensure idempotent at-least-once processing for multi-hour OCR/embedding backfill jobs.

*As of: 2026-11-02 (primary docs confirmed current as of ms.date 2026-09-16 and 2026-09-01; permission-change rollout confirmed as in-progress on 2026-11-02)*

**Sources**
- [Jobs in Azure Container Apps | Microsoft Learn](https://learn.microsoft.com/en-us/azure/container-apps/jobs) (official-docs) -- "Azure Container Apps jobs enable you to run containerized tasks that run for a finite duration and then stop... A job's trigger type determines how the job is started. ... Manual, Schedule, Event."
- [az containerapp job | Microsoft Learn](https://learn.microsoft.com/en-us/cli/azure/containerapp/job?view=azure-cli-latest) (official-docs) -- "ms.date: 2026-09-01 ... az containerapp job"
- [[IMPORTANT] Update permissions for Azure Container Apps job execution overrides · Issue #1872 · microsoft/azure-container-apps](https://github.com/microsoft/azure-container-apps/issues/1872) (repo) -- "Starting a job with container or init-container overrides now requires both Microsoft.App/jobs/start/action and Microsoft.App/jobs/write permissions... fully active across all production regions within two weeks... an empty array ([]) still counts as an override."
- [azure-mgmt-appcontainers 5.1.0 uses unsupported API version 2026-07-01 for Container Apps Jobs · Issue #49044 · Azure/azure-sdk-for-python](https://github.com/Azure/azure-sdk-for-python/issues/49044) (repo) -- "Version 5.1.0 sends the request using API version 2026-07-01 ... this newer API version is not yet registered for the Microsoft.App/jobs resource type in all regions."
- [Microsoft.App/jobs - Bicep, ARM template & Terraform AzAPI reference | Microsoft Learn](https://learn.microsoft.com/en-us/azure/templates/microsoft.app/jobs) (official-docs) -- "Azure Microsoft.App/jobs syntax and properties to use in Azure Resource Manager templates for deploying the resource. API version latest"


### Official documentation: Azure Container Registry
*Find the OFFICIAL documentation for "Azure Container Registry": its current stable version, how it is installed or enabled, the API surface this build will use, and any breaking changes or pitfalls in the last 18 months, prioritising current state as of Nov 2026.*

Azure Container Registry (ACR) is a managed Docker/OCI registry; for this build it is deployed via Bicep (Microsoft.ContainerRegistry/registries, stable API 2025-11-01) with Basic/Standard/Premium SKUs, authenticated via Microsoft Entra RBAC (not the legacy admin account), and consumed by the bot/review Container Apps and ingest/backfill Container Apps Jobs to pull images. No GCP project IDs are needed in ACR config, satisfying acceptance criterion 8. Classic (unSKU'd) registries are retired, Docker Content Trust is being deprecated in favor of Notary Project/Notation, and legacy Helm repositories were fully retired in March 2025 -- none of this affects a plain docker-push/pull CI/CD flow.

**Key findings**
- ACR is a managed registry based on the Docker platform, offered in three tiers (SKUs): Basic, Standard, Premium; Premium adds geo-replication and Private Link (per container-registry-intro, ms.date 2026-02-11).
- Authentication is via Azure CLI/docker login, Microsoft Entra service principal or managed identity, or a discouraged admin account; RBAC (and optional ABAC scoped to repositories) assigns push/pull without full registry control (per container-registry-intro and container-registry-faq, ms.date 2026-02-04/2026-02-11).
- Latest stable ARM/Bicep API version for Microsoft.ContainerRegistry/registries is 2025-11-01 (newest preview listed is 2026-09-01-preview), per the official allversions reference page.
- Docker Content Trust (DCT) deprecation started 2025-03-31; DCT can still be enabled on registries that never had it until 2026-05-31; full removal is 2028-03-31. Microsoft's recommended replacement is Notary Project/Notation signing via Azure Key Vault.
- Legacy Helm repository support (non-OCI Helm charts) and the 'az acr helm' CLI group were fully retired by 2025-03-30; classic (pre-SKU) registries are no longer supported at all, per the official FAQ.
- Older ACR REST API versions (2016-06-27-preview, 2017-06-01-preview, 2018-02-01-preview) lost support in October 2023; the 2017-03-01-GA version's support ends September 2026, so new deployments should target a current API version, per the official FAQ.
- Private Link/private endpoints for ACR are documented as a current Premium-tier feature (dedicated article, ms.date 2026-02-11) with a 200 private-endpoint cap and specific subnet IP-planning guidance for geo-replicated registries; note the separate intro overview page still labels this feature '(preview)' in its summary text even though the dedicated how-to treats it as available -- treat the dedicated article as authoritative.

**Recommendations**
- Deploy ACR via Bicep using the current stable API version (2025-11-01 or newer) with Basic or Standard SKU for a single-registry, low-replica setup (Premium only needed if geo-replication/Private Link/CMK is required); parameterize SKU, name, and location -- no hardcoded GCP project IDs.
- Disable the local admin account (adminUserEnabled: false) and grant AcrPull to the Container Apps' managed identities (bot, review) and AcrPush to the CI/CD identity, per Entra RBAC guidance; avoid az acr credential show-based admin credentials in any script.
- Do not adopt Docker Content Trust for new image signing; if image signing is required, use Notary Project/Notation with Azure Key Vault-held keys instead, since DCT is mid-deprecation.
- Reference the 'allversions' API list before pinning an apiVersion in Bicep so the pipeline doesn't drift onto a version nearing its Sept 2026 support cutoff (applies to 2017-03-01-GA specifically, not newer versions).
- Skip ACR Tasks/agent pools and Helm repository features entirely -- they are unused by this build and Helm repos are already retired.

**current version:** ARM/Bicep resource API 2025-11-01 (stable); service tiers Basic/Standard/Premium

**api surface**
- Bicep resource Microsoft.ContainerRegistry/registries (apiVersion 2025-11-01), properties: sku.name, adminUserEnabled, publicNetworkAccess
- Entra RBAC role assignments: AcrPull (Container Apps managed identities), AcrPush (CI/CD identity)
- az acr login / docker login, docker push, docker pull against <registry>.azurecr.io
- Docker Registry HTTP API V2 at https://<registry>.azurecr.io/v2/ (used implicitly by docker/Container Apps pulls)
- az acr show-usage / az acr check-health (operational diagnostics, optional)

**pitfalls**
- Classic (pre-SKU) registries are no longer supported -- must create/already use Basic, Standard, or Premium tier.
- Legacy Helm repository functionality and 'az acr helm' CLI group were fully retired 2025-03-30; store any Helm charts as OCI artifacts instead.
- Docker Content Trust is mid-deprecation (started 2025-03-31, can still be newly enabled until 2026-05-31, fully removed 2028-03-31) -- new signing work should use Notary Project/Notation, not DCT.
- Disabling public network access on a registry breaks 'az acr build' unless a dedicated agent pool or the AzureContainerRegistry service tag is allowlisted -- relevant only if private networking is added later.
- Admin account is single-user and discouraged for multi-service access; use RBAC/managed identity for Container Apps pulls instead.
- ACR API versions 2016-06-27-preview/2017-06-01-preview/2018-02-01-preview are already unsupported (since Oct 2023) and 2017-03-01-GA loses support Sept 2026 -- pin Bicep to a current (2025-11-01+) apiVersion.

*As of: Docs pages read ms.date 2026-02-04 to 2026-02-11, allversions page updated_at 2026-09-21; current as of November 2026*

**Sources**
- [Introduction to Azure Container Registry](https://learn.microsoft.com/en-us/azure/container-registry/container-registry-intro) (official-docs) -- "Container registries are available in three tiers (SKUs): Basic, Standard, and Premium... Premium registries support additional capabilities and have greater storage and limits."
- [Azure Container Registry FAQ](https://learn.microsoft.com/en-us/azure/container-registry/container-registry-faq) (official-docs) -- "The following API versions have been deprecated... 2017-03-01-GA | September 2023 | September 2026... Classic registries are no longer supported."
- [Transition from Docker Content Trust to Notary Project](https://learn.microsoft.com/en-us/azure/container-registry/container-registry-content-trust-deprecation) (official-docs) -- "deprecation of DCT started on March 31, 2025. DCT will be completely removed from Azure Container Registry on March 31, 2028."
- [Set Up Private Endpoint with Private Link for ACR](https://learn.microsoft.com/en-us/azure/container-registry/container-registry-private-endpoints) (official-docs) -- "This feature is available in the Premium container registry service tier (SKU), with a maximum of 200 private endpoints."
- [Microsoft.ContainerRegistry/registries - all versions](https://learn.microsoft.com/en-us/azure/templates/microsoft.containerregistry/allversions) (official-docs) -- "Microsoft.ContainerRegistry/registries | ...[2025-11-01]...[2026-01-01-preview][2026-03-01-preview][2026-09-01-preview]"


### Official documentation: Azure Key Vault
*Find the OFFICIAL documentation for "Azure Key Vault": its current stable version, how it is installed or enabled, the API surface this build will use, and any breaking changes or pitfalls in the last 18 months, prioritising current state as of Nov 2026.*

Azure Key Vault secrets management is accessed from this FastAPI build via the Python SDK `azure-keyvault-secrets` (current stable 4.12.0, released 2026-10-27) together with `azure-identity`'s `DefaultAzureCredential`, which works unchanged locally and under Container Apps managed identity. The vault itself is provisioned via Bicep (`Microsoft.KeyVault/vaults`) with `enableRbacAuthorization: true`, since RBAC is now the default permission model for newly created vaults as of API version 2026-02-01, replacing legacy access policies. The bot/ingest/backfill Container Apps get a system-assigned managed identity granted the built-in 'Key Vault Secrets User' role at vault scope and call `get_secret`/async `get_secret` with no secrets ever written to the repo.

**Key findings**
- azure-keyvault-secrets current stable is 4.12.0 (released 2026-10-27 per official CHANGELOG), requiring Python 3.10+; install with `pip install azure-keyvault-secrets azure-identity`.
- 4.12.0 is a breaking release: dropped Python 3.9 support; default REST API version bumped to 2026-04-01; hardened auth-challenge caching against injection.
- 4.10.0 (2025-06-16) had earlier dropped Python 3.8; 4.11.0 (2026-03-26) added `out_content_type` on get_secret and `previous_version` on SecretProperties.
- Core client: `SecretClient(vault_url, credential)` with methods get_secret, set_secret, update_secret_properties, begin_delete_secret, list_properties_of_secrets; async variant in `azure.keyvault.secrets.aio`.
- Starting with Key Vault API version 2026-02-01, Azure RBAC (not vault access policies) is the default data-plane access model for newly created vaults.
- Switching an existing vault's permission model from access-policy to RBAC invalidates ALL access-policy grants immediately -- can cause outages if roles aren't pre-staged.
- Secrets are capped at 25 KB per value; the official docs explicitly say Key Vault is optimized for cryptographic secrets, not general app configuration.
- Container Apps expose managed-identity tokens via IDENTITY_ENDPOINT/IDENTITY_HEADER env vars; DefaultAzureCredential consumes these automatically with no code changes between local dev and Azure.
- Managed-identity token cache is per resource URI for ~24h; a newly granted role assignment may not take effect immediately if a token was already cached.
- ABAC conditions scoping Key Vault secret access by name/vault pattern are still in preview, not GA.

**Recommendations**
- Implement the secrets/config swap point as a thin SecretProvider interface; Azure impl wraps SecretClient+DefaultAzureCredential, GCP impl wraps google-cloud-secret-manager, so removing GCP later (criterion 11) is a file deletion, not a rewrite.
- Provision the vault in Bicep with enableRbacAuthorization: true and grant each Container App's system-assigned identity only 'Key Vault Secrets User' (read-only); reserve 'Key Vault Secrets Officer' for the not-yet-executed migration/cutover identity.
- Pin azure-keyvault-secrets>=4.11,<5 and azure-identity; confirm the Container Apps base image runs Python 3.10+ given 4.12.0 dropped 3.9.
- Keep only true secrets (WhatsApp token, DB password, model API keys) in Key Vault; leave pricing.py price tables, model names, and feature flags in pydantic-settings/env vars per Microsoft's own 'not for general configuration' guidance.
- In the scripted (not-executed) cutover plan, pre-stage all Key Vault role assignments before any identity or permission-model switch, and account for the ~24h managed-identity token cache when validating the parallel run.
- If using the async FastAPI path, install an async transport (e.g. aiohttp) alongside azure.keyvault.secrets.aio.SecretClient rather than mixing sync calls into async request handlers.

**current version:** 4.12.0 (azure-keyvault-secrets, Python SDK, released 2026-10-27)

**api surface**
- azure.keyvault.secrets.SecretClient(vault_url, credential) / aio.SecretClient for async
- azure.identity.DefaultAzureCredential() (sync and .aio async variant)
- SecretClient.get_secret(name) -> KeyVaultSecret.value
- SecretClient.set_secret(name, value) -- used only by the scripted, not-yet-executed migration tooling
- SecretClient.list_properties_of_secrets() -- enumeration without values
- azure.core.exceptions.ResourceNotFoundError for missing-secret handling
- Bicep: Microsoft.KeyVault/vaults with enableRbacAuthorization: true; Microsoft.Authorization/roleAssignments for 'Key Vault Secrets User'/'Secrets Officer'
- Container App identity block (Bicep): identity: { type: 'SystemAssigned' }

**pitfalls**
- 4.12.0 drops Python 3.9 support (3.10+ required) -- check container base image before upgrading the SDK.
- New vaults default to RBAC (API version 2026-02-01+); flipping an existing vault's model to RBAC invalidates all access-policy grants instantly.
- Managed-identity tokens are cached ~24h per resource URI; freshly granted roles may not be honored immediately during cutover testing.
- Key Vault secret values capped at 25 KB; not designed as a general config/feature-flag store.
- ABAC-based fine-grained secret scoping is still preview, not production-GA.
- Async SecretClient needs an installed async HTTP transport (e.g. aiohttp); omitting it silently breaks async usage.

*As of: 2026-10-28 (Learn docs refresh); SDK 4.12.0 released 2026-10-27; RBAC-default change effective with API version 2026-02-01*

**Sources**
- [Azure Key Vault Secrets client library for Python | Microsoft Learn](https://learn.microsoft.com/en-us/python/api/overview/azure/keyvault-secrets-readme?view=azure-python) (official-docs) -- "Python 3.10 or later is required to use this package... pip install azure-keyvault-secrets azure-identity"
- [azure-keyvault-secrets CHANGELOG (Azure/azure-sdk-for-python)](https://github.com/Azure/azure-sdk-for-python/blob/main/sdk/keyvault/azure-keyvault-secrets/CHANGELOG.md) (official-docs) -- "4.12.0 ... Breaking Change: Python 3.9 is no longer supported. Please use Python 3.10 or later"
- [Grant permission to applications to access an Azure key vault using Azure RBAC | Microsoft Learn](https://learn.microsoft.com/en-us/azure/key-vault/general/rbac-guide) (official-docs) -- "Starting with API version 2026-02-01, Azure RBAC is the default access control model for newly created key vaults."
- [Managed identities in Azure Container Apps | Microsoft Learn](https://learn.microsoft.com/en-us/azure/container-apps/managed-identity) (official-docs) -- "Container Apps provides an internally accessible REST endpoint... IDENTITY_ENDPOINT... IDENTITY_HEADER... the Azure Identity client library provides an abstraction over this REST endpoint."


### Official documentation: Azure Managed Identity
*Find the OFFICIAL documentation for "Azure Managed Identity": its current stable version, how it is installed or enabled, the API surface this build will use, and any breaking changes or pitfalls in the last 18 months, prioritising current state as of Nov 2026.*

Azure Managed Identity (part of Microsoft Entra ID) is a platform feature, not a versioned library, that lets Azure compute (Container Apps, Container Apps Jobs) obtain Entra tokens with zero stored credentials; the build's config/secrets seam should use the Python `azure-identity` SDK (current stable 1.27.0, released 2026-10-26) via `DefaultAzureCredential`/`ManagedIdentityCredential`, with a user-assigned identity attached in Bicep to the bot, review, ingest and backfill Container Apps/Jobs. This identity is then RBAC-authorized against Key Vault, Blob Storage, ACR, Azure OpenAI/Document Intelligence, and Postgres Flexible Server (Entra auth), replacing GCP service-account JSON keys. Key operational gotchas: explicit `client_id` is required for user-assigned identities, RBAC propagation can be cached up to ~24h, and Postgres Entra tokens for managed identities last up to 24h (user tokens only 1h) so connection/token refresh logic is needed.

**Key findings**
- azure-identity Python SDK current stable version is 1.27.0, released 2026-10-26, requires Python 3.10+ or a non-EOL Python 3 (per learn.microsoft.com identity-readme, ms.date 2026-10-26).
- Two managed identity types: system-assigned (tied to one resource's lifecycle) and user-assigned (standalone resource, shareable across multiple Container Apps/Jobs); user-assigned is Microsoft's recommended type for services sharing an identity.
- Container Apps are configured via Bicep `identity: { type: 'UserAssigned', userAssignedIdentities: { '<id>': {} } }` (or `'SystemAssigned'`/`'SystemAssigned,UserAssigned'`); CLI equivalent is `az containerapp identity assign/show/remove`.
- Container Apps expose an internal token endpoint via `IDENTITY_ENDPOINT`/`IDENTITY_HEADER` env vars (api-version 2019-08-01+); the Python azure-identity library abstracts this via `DefaultAzureCredential`/`ManagedIdentityCredential`.
- To use a user-assigned identity, you must pass one of `client_id` (preferred for azure-identity), `principal_id`/`object_id`, or `mi_res_id` -- omitting all defaults to the system-assigned identity, which may not exist and fail silently/confusingly.
- Starting API version 2024-02-02-preview, Container Apps support per-identity lifecycle scoping (`Init`/`Main`/`All`/`None`) to restrict which containers (init vs main) can use a given managed identity; currently only `Init` is limited to workload-profile consumption environments.
- RBAC role-assignment back-end cache for managed identity target resources persists ~24 hours; a freshly granted role may not take effect immediately and forced refresh isn't supported (per Container Apps managed-identity doc, updated_at 2026-02-13).
- `DefaultAzureCredential` continuation policy (since azure-identity 1.14.0): developer credentials are tried in sequence regardless of individual failures, but deployed-service credentials (e.g. managed identity in Container Apps) throw immediately on failed token retrieval -- this governs how local dev vs Azure-hosted auth paths differ.
- For Azure Database for PostgreSQL Flexible Server, Microsoft Entra/managed-identity auth uses the token as the connection password; user Entra tokens are valid up to 1 hour, but tokens for system-assigned managed identities are valid up to 24 hours (per postgresql/security/security-entra-concepts, ms.date 2026-07-14).
- Init containers cannot use managed identity at all in consumption-only or dedicated workload-profile Container Apps environments (hard platform limitation, not a 2026 change).

**Recommendations**
- Use a single user-assigned managed identity (not system-assigned) shared across the bot, review, ingest and backfill Container Apps/Jobs so Bicep can grant RBAC once and reuse it, matching Microsoft's recommendation for multi-resource workloads.
- In the secrets/config abstraction, construct credentials via `DefaultAzureCredential(managed_identity_client_id=<uami client id>)` so the same code path works locally (falls back to Azure CLI credential) and in Azure (uses the managed identity) without branching.
- For the Postgres Flexible Server seam, do not cache a DB access token longer than its lifetime; refresh the Entra token per new connection/pool checkout rather than only at app startup, given the 1-24h token lifetime limits.
- Grant RBAC roles (Key Vault Secrets User, Storage Blob Data Contributor, AcrPull, Cognitive Services User for Azure OpenAI/Document Intelligence) in the same Bicep deployment that creates the identity, and allow for eventual-consistency delay (up to ~24h cache) when testing immediately after a fresh role assignment.
- Do not hardcode a managed identity's `client_id`/`principal_id` as a fallback default in code; always require it be passed explicitly in config, since omitting all ID parameters silently targets the system-assigned identity.
- Keep this fully reversible per the locked plan: managed identity + RBAC is additive infrastructure (Bicep, parameterized by subscription/resource names) and does not touch the live GCP system; no credentials from this identity need to be written to the repo.

**current version:** No version applies to the Managed Identity platform feature itself; the Python client library that consumes it, azure-identity, is at stable 1.27.0 (released 2026-10-26, verified on PyPI and Microsoft Learn).

**api surface**
- azure.identity.DefaultAzureCredential(managed_identity_client_id=<uami_client_id>) -- primary credential object for the secrets/config seam
- azure.identity.ManagedIdentityCredential(client_id=<uami_client_id>) -- direct managed-identity credential when chaining is not needed
- azure.identity.aio.DefaultAzureCredential / ManagedIdentityCredential -- async variants for FastAPI async code paths
- Bicep: identity: { type: 'UserAssigned', userAssignedIdentities: { '<identity_resource_id>': {} } } on Container Apps and Container Apps Jobs
- az containerapp identity assign|show|remove --user-assigned <id> (operational/debugging, not app runtime)
- Container Apps internal token endpoint: GET $IDENTITY_ENDPOINT?resource=<aad-resource-uri>&client_id=<id>&api-version=2019-08-01, header X-IDENTITY-HEADER: $IDENTITY_HEADER (used transparently by azure-identity)
- RBAC role assignment on target resources (Key Vault, Storage account, ACR, Azure OpenAI/Document Intelligence, Postgres Flexible Server Entra admin) authorizing the identity's principal ID
- Postgres Flexible Server Entra/managed-identity auth: obtain token for resource 'https://ossrdbms-aad.database.windows.net/.default' and use it as the connection password

**pitfalls**
- Omitting client_id/principal_id/mi_res_id when requesting a token for a user-assigned identity silently falls back to attempting the system-assigned identity, which may not exist -- always pass the client_id explicitly.
- RBAC grants to a managed identity can take effect with a delay due to a ~24h token cache on the target resource's back end; forced refresh isn't supported, so parallel-run testing should allow for this lag.
- azure-identity 1.14.0+ changed DefaultAzureCredential's continuation behavior for developer credentials (keeps trying chain on failure) vs deployed credentials (throws immediately) -- affects local-dev-vs-Azure-hosted debugging expectations.
- azure-identity drops support for end-of-life Python versions as a matter of policy; current release requires Python 3.10+, so the ~6k LOC app's Python version must be compatible before pinning this SDK.
- Init containers cannot use managed identity at all in consumption-only or dedicated workload-profile Container Apps environments; fine-grained Init/Main/All/None lifecycle scoping needs API version 2024-02-02-preview and only partially supports workload-profile consumption environments.
- Postgres Flexible Server Entra tokens expire (1h for user tokens, up to 24h for system-assigned managed identity tokens); a long-lived SQLAlchemy connection pool must refresh the token rather than reuse a stale one past expiry.
- Continuous Access Evaluation (CAE) and brokered (WAM) authentication are explicitly not supported for managed identity credentials -- don't assume CAE-protected resources work transparently through a managed identity.

*As of: 2026-10-26 (azure-identity Python SDK readme, PyPI 1.27.0); 2026-02-13 (Container Apps managed identity doc updated_at); 2026-09-06 (Postgres Flexible Server Entra auth concepts doc updated_at); 2026-06-15 (Entra ID managed identities overview doc updated_at)*

**Sources**
- [Managed identities for Azure resources - overview](https://learn.microsoft.com/en-us/entra/identity/managed-identities-azure-resources/overview) (official-docs) -- "A managed identity is an identity that can be assigned to an Azure compute resource ... Once a managed identity is assigned on the compute resource, it can be authorized, directly or indirectly, to access downstream dependency resources ... Managed identity replaces secrets such as access keys or passwords."
- [Managed identities in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/managed-identity) (official-docs) -- "Starting in API version 2024-02-02-preview, you can control which managed identities are available to your container app during the init and main phases ... The back-end services for managed identities maintain a cache per resource URI for around 24 hours."
- [Azure Identity client library for Python](https://learn.microsoft.com/en-us/python/api/overview/azure/identity-readme?view=azure-python) (official-docs) -- "Source code | Package (PyPI) ... azure-identity_1.27.0 ... Python 3.10 or a recent version of Python 3 (this library doesn't support end-of-life versions). As of version 1.14.0, DefaultAzureCredential attempts to authenticate with all developer credentials until one succeeds..."
- [azure-identity · PyPI](https://pypi.org/project/azure-identity/) (official-docs) -- "current latest version of the azure-identity package is 1.27.0, released on October 26, 2026"
- [Microsoft Entra Authentication in Azure Database for PostgreSQL Flexible Server](https://learn.microsoft.com/en-us/azure/postgresql/security/security-entra-concepts) (official-docs) -- "User tokens are valid for up to 1 hour. Tokens for system-assigned managed identities are valid for up to 24 hours."
- [Managed Identities in Azure Database for PostgreSQL Flexible Server](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/security-managed-identity-overview) (official-docs) -- "An Azure Database for PostgreSQL uses system assigned managed identity for: azure_storage extension ... Use user assigned managed identities ... for: Data encryption with customer managed keys."


### Official documentation: Microsoft Graph API
*Find the OFFICIAL documentation for "Microsoft Graph API": its current stable version, how it is installed or enabled, the API surface this build will use, and any breaking changes or pitfalls in the last 18 months, prioritising current state as of Nov 2026.*

Microsoft Graph is a single REST API surface (base https://graph.microsoft.com) with two endpoints: v1.0 (stable/GA, use for production) and beta (preview, breaking changes without notice). For this build's Microsoft Graph importer, the relevant surface is driveItem listing/download under SharePoint document libraries and OneDrive (via /sites/{siteId}/drive and /drives/{drive-id}/items), authenticated app-only via OAuth2 client credentials (no signed-in user, suited to a Container Apps Job). Install via the official Python SDK package msgraph-sdk (current PyPI version 1.65.0, released 2026-10-22) layered on azure-identity credential classes. A critical pitfall for acceptance criterion 10: the Graph API's own sha256Hash field on driveItem is explicitly documented as unsupported, so the importer must compute SHA-256 locally after downloading file content rather than relying on Graph-provided hashes.

**Key findings**
- v1.0 is the current stable endpoint (https://graph.microsoft.com/v1.0); beta is preview-only and 'not supported' for production use per the official overview page (ms.date 2024-07-16, content current through at least 2026-10 per linked what's-new page).
- Versioning policy page (updated_at 2025-08-06) states: 'Currently, no versions of Microsoft Graph are deprecated or unsupported' and deprecations require 24 months' advance notice.
- driveItem content download: GET /drives/{drive-id}/items/{item-id}/content (also /sites/{siteId}/drive/items/{item-id}/content for SharePoint) returns HTTP 302 redirecting to a preauthenticated, time-limited download URL (expires within minutes) — must follow the redirect immediately, not cache the URL.
- Required Graph application permissions for app-only (daemon) file/site access: least-privileged Files.Read.All, or Sites.Read.All for broader SharePoint site access; both require tenant admin consent.
- App-only auth flow: POST https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token with grant_type=client_credentials and scope=https://graph.microsoft.com/.default (per auth-v2-service doc, ms.date 2025-08-29) — this is the 'background service/daemon' pattern, matching a Container Apps Job with no signed-in user.
- Official Python SDK package is msgraph-sdk on PyPI, current version 1.65.0 (released 2026-10-22), requires Python >=3.10, uses GraphServiceClient and azure-identity credential classes (e.g. ClientSecretCredential) for auth.
- driveItem file hashes facet: sha256Hash property is explicitly documented as 'This property isn't supported. Don't use.' Only quickXorHash is guaranteed available across OneDrive consumer and work/school; sha1Hash and crc32Hash are 'if available' only.
- [uncertain] Could not open the live Graph API changelog page (developer.microsoft.com/graph/changelog) in enough detail to extract specific dated 2025–2026 breaking-change entries for Files/SharePoint/driveItem; the versioning policy page itself reports no currently deprecated versions, but item-level changelog entries were not individually verified.

**Recommendations**
- Use the v1.0 endpoint only (never beta) for the SharePoint/OneDrive importer, per Microsoft's explicit production guidance.
- Authenticate with the OAuth2 client credentials grant via azure-identity's ClientSecretCredential (or a managed identity if supported for the tenant), requesting scope https://graph.microsoft.com/.default — matches the existing provider-neutral secrets abstraction (acceptance criterion 2) and the no-signed-in-user Container Apps Job context.
- Request least-privileged application permissions (Files.Read.All, or Sites.Read.All only if cross-site listing is needed) and get tenant admin consent before first run; re-consent whenever permissions change.
- Do NOT dedupe using Graph's sha256Hash field — it is documented as unsupported. Download file content via GET .../content, then compute SHA-256 locally in Python and compare against stored hashes to satisfy acceptance criterion 10.
- Treat the @microsoft.graph.downloadUrl / 302 redirect target as ephemeral: fetch driveItem metadata, immediately follow/download, don't persist the download URL for retry logic.
- Pin msgraph-sdk and azure-identity versions in requirements and note the SDK is large (~36MB) — account for this in Container Apps Job image build time.
- Before building, pull the live Microsoft Graph API changelog (developer.microsoft.com/graph/changelog, filtered to v1.0) directly rather than relying on this summary, since granular 2025–2026 Files/SharePoint changelog entries were not independently verified here.

**current version:** Microsoft Graph v1.0 endpoint (stable/GA); beta endpoint for preview APIs. Python SDK (msgraph-sdk) is at 1.65.0 as of 2026-10-22.

**api surface**
- OAuth2 client credentials token request: POST https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token (grant_type=client_credentials, scope=https://graph.microsoft.com/.default)
- GET /sites/{siteId}/drive or /sites/{siteId}/drives — resolve SharePoint document library drive
- GET /drives/{drive-id}/items/{item-id}/children or /drives/{drive-id}/root/children — list files/folders in SharePoint/OneDrive
- GET /drives/{drive-id}/items/{item-id}/content — download primary file content (follow 302 redirect)
- driveItem resource fields: id, name, size, lastModifiedDateTime, file.hashes.quickXorHash (for change detection only, not sha256)
- msgraph-sdk Python: GraphServiceClient with azure.identity.ClientSecretCredential (or aio variant) as auth provider
- Application permissions: Files.Read.All and/or Sites.Read.All, admin-consented in Entra ID app registration

**pitfalls**
- driveItem hashes.sha256Hash is documented as unsupported — do not use it for dedup; compute SHA-256 locally from downloaded bytes.
- Only quickXorHash is guaranteed present across OneDrive personal and work/school; other hash fields are 'if available' only.
- /content endpoint's download URL is a time-limited preauthenticated redirect (expires within minutes) — must be consumed immediately, not cached or retried later.
- beta endpoint APIs can break or be removed without notice and are explicitly unsupported for production — restrict the importer to v1.0.
- Application (app-only) permissions always require tenant admin consent, and any permission change requires re-consent — plan this into the deployment/runbook, not just code.
- [uncertain] Detailed 2025–2026 changelog entries specific to Files/SharePoint/driveItem endpoints were not individually confirmed by opening the live Graph changelog; verify directly against developer.microsoft.com/graph/changelog before relying on current driveItem behavior for edge cases.

*As of: Nov 2026 — msgraph-sdk (Python) 1.65.0 released 2026-10-22; Graph what's-new-overview page content dated/updated through 2026-10-31; versioning-and-support page updated 2025-08-06; auth-v2-service page updated 2025-08-29; overview/driveitem-get-content/hashes reference pages dated 2024 but still canonical per current Microsoft Learn site*

**Sources**
- [Microsoft Graph REST API v1.0 endpoint reference](https://learn.microsoft.com/en-us/graph/api/overview?view=graph-rest-1.0) (official-docs) -- "API sets on the v1.0 endpoint (https://graph.microsoft.com/v1.0) have reached general availability (GA)... Updates to APIs on this endpoint are additive in nature and don't break existing app scenarios."
- [Versioning, support, and breaking change policies for Microsoft Graph](https://learn.microsoft.com/en-us/graph/versioning-and-support) (official-docs) -- "Currently, no versions of Microsoft Graph are deprecated or unsupported."
- [Download driveItem content - Microsoft Graph v1.0](https://learn.microsoft.com/en-us/graph/api/driveitem-get-content?view=graph-rest-1.0) (official-docs) -- "Returns a 302 Found response redirecting to a preauthenticated download URL for the file... Preauthenticated download URLs are valid for a limited time. Use them immediately, as they might expire within minutes."
- [hashes resource type - Microsoft Graph v1.0](https://learn.microsoft.com/en-us/graph/api/resources/hashes?view=graph-rest-1.0) (official-docs) -- "sha256Hash | String | This property isn't supported. Don't use."
- [Get access without a user - Microsoft Graph](https://learn.microsoft.com/en-us/graph/auth-v2-service) (official-docs) -- "scope=https%3A%2F%2Fgraph.microsoft.com%2F.default ... grant_type=client_credentials ... Background services (daemons) that run on a server without a signed-in user."
- [Install a Microsoft Graph SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation?tabs=python) (official-docs) -- "pip install msgraph-sdk"
- [msgraph-sdk · PyPI](https://pypi.org/project/msgraph-sdk/) (official-docs) -- "Current Version: 1.65.0, Release Date: October 22, 2026, requires Python >=3.10"
- [What's new in Microsoft Graph](https://learn.microsoft.com/en-us/graph/whats-new-overview) (official-docs) -- "ms.date: 2026-10-06 ... updated_at: 2026-10-31"


### Official documentation: SharePoint
*Find the OFFICIAL documentation for "SharePoint": its current stable version, how it is installed or enabled, the API surface this build will use, and any breaking changes or pitfalls in the last 18 months, prioritising current state as of Nov 2026.*

SharePoint document libraries are consumed via the Microsoft Graph REST API v1.0 (GA, no separate version number), exposed as 'drive'/'driveItem' resources identical to OneDrive. For this build's importer, the relevant surface is: get the site's drive, list/track files via driveItem delta, and download content via /content or @microsoft.graph.downloadUrl. Access requires an Entra ID app registration using client-credentials (application permissions Files.Read.All/Sites.Read.All, or least-privilege Sites.Selected scoped to one site) — the old SharePoint Add-in/Azure ACS app-only model is now fully retired (April 2, 2026) and unusable. A critical pitfall for this build: Graph's file.hashes.sha256Hash property is explicitly documented as unsupported, so the sha256 de-dup required by the build must be computed locally from downloaded bytes, not read from Graph.

**Key findings**
- SharePoint document libraries are accessed as OneDrive 'drive' resources; files/folders are 'driveItem' resources (learn.microsoft.com/graph/sharepoint-concept-overview, ms.date 2024-11-07, updated 2025-08-06).
- driveItem resource page (updated_at 2026-10-08) lists methods: Get item, List children, Download file (driveitem-get-content), Upload, Track changes (delta), Create upload session, etc.
- Download content: GET /sites/{siteId}/drive/items/{item-id}/content (or /drives/{drive-id}/items/{item-id}/content) returns HTTP 302 to a preauthenticated downloadUrl; this URL requires no Authorization header but expires quickly ('might expire within minutes'); supports Range for partial downloads (page updated_at 2025-08-27).
- Incremental sync uses GET /drives/{drive-id}/root/delta (or /sites/{siteId}/drive/root/delta); responses page via @odata.nextLink then end with @odata.deltaLink; stale tokens return HTTP 410 Gone with resync error codes resyncChangesApplyDifferences/resyncChangesUploadDifferences; items must be tracked by id, not path (page updated_at 2026-06-06).
- Application (app-only) permissions for delta/content: least-privileged Files.Read.All, higher-privileged Files.ReadWrite.All/Sites.Read.All/Sites.ReadWrite.All (per the delta and get-content reference pages).
- hashes resource (file facet) properties: crc32Hash, quickXorHash, sha1Hash, sha256Hash — the page states explicitly: 'sha256Hash ... This property isn't supported. Don't use.' quickXorHash is the only hash 'guaranteed to be available for both OneDrive for work or school and OneDrive for home' (page updated_at 2025-04-09).
- Sites.Selected (and the newer *.SelectedOperations.Selected tuple scopes) let an app be consented tenant-wide but only actually access a site/list/file after an explicit POST /sites/{siteId}/permissions grant with a role (read/write/owner/fullcontrol) — a 3-step model (consent + grant + token) distinct from always-on scopes like Files.Read.All (permissions-selected-overview, updated_at 2026-02-26).
- SharePoint Add-ins (SharePoint-hosted and provider-hosted) and Azure ACS app-only authentication for SharePoint Online fully retired and stopped working on April 2, 2026; this is in the past relative to the Nov 2026 research date. CSOM/JSOM/SharePoint REST APIs are not retired, but any auth must now be Microsoft Entra ID-based, not ACS (add-ins-and-azure-acs-retirements-faq, ms.date 2026-10-25, updated_at 2026-10-28).

**Recommendations**
- Build the SharePoint/OneDrive importer against Microsoft Graph v1.0 REST only (driveItem/delta/content); do not use legacy SharePoint CSOM/Add-in/ACS auth, which is now retired.
- Register an Entra ID app and authenticate via client-credentials (application permissions). Prefer scoping access to just the school's one SharePoint document library using Sites.Selected plus an explicit POST /sites/{siteId}/permissions grant, falling back to Files.Read.All only if Sites.Selected setup proves impractical for the school's tenant admin.
- Enumerate files via drive root delta rather than paging children, so no files are missed under concurrent writes; persist the deltaLink per drive to support later incremental re-ingest runs; handle HTTP 410 Gone by doing a full resync per Microsoft's documented resync codes.
- Download each file's bytes via the /content endpoint (or the short-lived @microsoft.graph.downloadUrl) immediately — do not cache the download URL across job runs/retries since it can expire within minutes.
- Compute the sha256 hash for duplicate detection yourself from the downloaded byte stream. Do NOT read or rely on driveItem file.hashes.sha256Hash — Microsoft's own docs say this field 'isn't supported' and should not be used.
- Track driveItem identity by id (not by path) in the ingest/backfill jobs, since delta's parentReference omits path and renames only show the latest state.

**current version:** Microsoft Graph REST API v1.0 (GA); no discrete version number — v1.0 is the current stable surface alongside the beta channel [uncertain]

**api surface**
- GET /sites/{siteId}/drive — resolve the SharePoint document library as a drive
- GET /drives/{drive-id}/root/delta — incremental enumeration of files/folders with @odata.deltaLink for future syncs
- GET /drives/{drive-id}/items/{item-id}/content (or follow @microsoft.graph.downloadUrl) — download file bytes
- driveItem fields used: id, name, size, lastModifiedDateTime, parentReference, file (for mimeType; not for sha256Hash)
- Entra ID client-credentials (application) permissions: Files.Read.All or Sites.Selected scoped via POST /sites/{siteId}/permissions [Sites.Selected setup details uncertain]

**pitfalls**
- file.hashes.sha256Hash is documented as unsupported ('Don't use') — never rely on it for the required sha256-based duplicate skip; compute the hash locally after download.
- SharePoint Add-in model and Azure ACS app-only auth for SharePoint Online are fully retired/EOL as of 2026-04-02; only Entra ID app registrations with Graph permissions work now.
- @microsoft.graph.downloadUrl / /content redirect URLs are short-lived (can expire within minutes) — don't persist or reuse them across retries.
- delta tokens can go stale, returning HTTP 410 Gone requiring a full resync; importer logic must handle resyncChangesApplyDifferences/resyncChangesUploadDifferences rather than assuming delta always succeeds.
- Selected scopes (Sites.Selected, etc.) require three separate steps (Entra consent + explicit /permissions grant + token) — forgetting the explicit site-permission grant leaves the app with zero access even after admin consent.

*As of: Nov 2026 (source pages dated/updated between 2024-11-07 and 2026-10-28; Graph REST surface is v1.0 GA, no separate release-version number)*

**Sources**
- [SharePoint sites and content API overview - Microsoft Graph](https://learn.microsoft.com/en-us/graph/sharepoint-concept-overview) (official-docs) -- "You can use the OneDrive API to work with a library as a drive, or the SharePoint API to work with it as a list."
- [driveItem resource type - Microsoft Graph v1.0](https://learn.microsoft.com/en-us/graph/api/resources/driveitem?view=graph-rest-1.0) (official-docs) -- "All file system objects in OneDrive and SharePoint are returned as driveItem resources."
- [driveItem: delta - Microsoft Graph v1.0](https://learn.microsoft.com/en-us/graph/api/driveitem-delta?view=graph-rest-1.0) (official-docs) -- "When using delta you should always track items by id. ... the service returns an HTTP 410 Gone error ... containing a new nextLink that starts a fresh delta enumeration from scratch."
- [File resource type - Microsoft Graph v1.0](https://learn.microsoft.com/en-us/graph/api/resources/file?view=graph-rest-1.0) (official-docs) -- "hashes | Hashes | Hashes of the file's binary content, if available. Read-only."
- [Download driveItem content - Microsoft Graph v1.0](https://learn.microsoft.com/en-us/graph/api/driveitem-get-content?view=graph-rest-1.0) (official-docs) -- "Preauthenticated download URLs are valid for a limited time. Use them immediately, as they might expire within minutes."
- [hashes resource type - Microsoft Graph v1.0](https://learn.microsoft.com/en-us/graph/api/resources/hashes?view=graph-rest-1.0) (official-docs) -- "sha256Hash | String | This property isn't supported. Don't use."
- [Overview of Selected Permissions in OneDrive and SharePoint - Microsoft Graph](https://learn.microsoft.com/en-us/graph/permissions-selected-overview) (official-docs) -- "Initially, Sites.Selected existed to restrict an application's access to a single site collection. ... Selected scopes require an explicit assignment action."
- [SharePoint Add-Ins and Azure ACS retirement FAQ](https://learn.microsoft.com/en-us/sharepoint/dev/sp-add-ins/add-ins-and-azure-acs-retirements-faq) (official-docs) -- "Using Azure ACS (Access Control Services) for SharePoint Online has been retired as of November 27th 2023 and will stop working from April 2nd 2026 ... SharePoint Add-ins reached end of life in SharePoint Online on April 2, 2026."


### Official documentation: OneDrive
*Find the OFFICIAL documentation for "OneDrive": its current stable version, how it is installed or enabled, the API surface this build will use, and any breaking changes or pitfalls in the last 18 months, prioritising current state as of Nov 2026.*

The relevant 'OneDrive' surface for this build is the Microsoft Graph v1.0 driveItem API (files live under SharePoint/OneDrive drives, addressed via /drives/{id}/items/{id}), accessed with app-only (client-credentials) auth via Entra ID. There is no separate 'OneDrive version' to install; it's a hosted REST API consumed over HTTPS, optionally via the official msgraph-sdk Python package (current 1.65.0, Oct 22 2026). The documented hashes facet explicitly marks sha256Hash as 'not supported, don't use' -- the importer must compute SHA-256 itself from downloaded bytes, not rely on Graph. A documented upcoming breaking change (tempauth/pre-authenticated download URL retirement, April 1 2027) affects the exact download pattern (302 redirect / @microsoft.graph.downloadUrl) this build would naturally use.

**Key findings**
- driveItem resource (v1.0) represents files/folders in OneDrive and SharePoint drives; addressed by /drives/{drive-id}/items/{item-id} or /drive/root:/path.
- List folder contents: GET /drives/{drive-id}/items/{item-id}/children (or /root/children); default page size 200, paginate via @odata.nextLink.
- Download content: GET /drives/{drive-id}/items/{item-id}/content returns HTTP 302 to a preauthenticated download URL (same as @microsoft.graph.downloadUrl); URL valid ~1 hour, no Authorization header needed on it today.
- hashes facet: sha256Hash property is explicitly documented as 'This property isn't supported. Don't use.' Only quickXorHash is guaranteed on both OneDrive consumer and work/school; sha1Hash is 'if available' only.
- App-only auth: OAuth2 client-credentials grant against POST https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token with scope=https://graph.microsoft.com/.default; requires admin consent on application permissions (least-privileged: Files.Read.All, plus Sites.Read.All for SharePoint document libraries).
- Official MS blog (Oct 2026): pre-authenticated 'tempauth' URLs (incl. @microsoft.graph.downloadUrl / the 302 target) are being retired by April 1, 2027 for SharePoint Online/OneDrive; affected ops include download, createUploadSession, previews, thumbnails, format conversion, long-running actions.
- After the 2027 retirement, apps must send an Entra ID bearer token directly against returned content URLs/endpoints instead of treating the URL as self-authenticating, and must not cache/store the download URL.
- Permission resource properties grantedTo/grantedToIdentities are being removed after a 4-year deprecation notice; use grantedToV2/grantedToIdentitiesV2 instead (relevant only if this build ever reads permissions, which it doesn't need to).
- msgraph-sdk (Python) current version 1.65.0, released 2026-10-22, requires Python >=3.10 (3.10-3.14 supported) -- optional; plain httpx/requests calls to the REST API also work and match this codebase's 'plain Python' style.

**Recommendations**
- Do not depend on Graph's hashes.sha256Hash for dedup -- it is documented unsupported. Download each file's bytes once and compute sha256 locally (hashlib.sha256) in the importer, matching AC#10 exactly.
- Use app-only auth: register an Entra ID app, grant application permissions Files.Read.All (plus Sites.Read.All if pulling from SharePoint doc libraries), get admin consent, and acquire tokens via the client_credentials flow (store client id/secret or cert in the existing secrets abstraction, never in repo).
- Call Graph directly over HTTPS (httpx) with Bearer tokens for simplicity and testability, rather than adding the full msgraph-sdk dependency, unless the team wants its typed models.
- When downloading content, follow the current 302/@microsoft.graph.downloadUrl pattern now, but do not persist/cache that URL anywhere -- fetch and discard immediately, since it's short-lived (~1hr) today and the mechanism itself is being retired by 2027.
- Design the download path so switching to a direct Authorization-header content fetch (post-tempauth-retirement) is a small change, not a rewrite -- i.e., keep the HTTP client call behind the same storage/import abstraction already planned for Blob/GCS.
- Paginate folder listings with @odata.nextLink; don't assume all files return in one page once past 200 items.
- Avoid the deprecated drive/sharedWithMe endpoint and legacy grantedTo/grantedToIdentities permission fields; this build's SharePoint/OneDrive import doesn't need either.

**current version:** Microsoft Graph REST API v1.0 (stable, no numeric version churn); official Python SDK msgraph-sdk 1.65.0 (2026-10-22)

**api surface**
- [removed by OSA: this line looked like an instruction aimed at an AI (exfiltration)]
- GET /sites/{site-id}/drive or /drives/{drive-id} to resolve the SharePoint/OneDrive document library drive
- GET /drives/{drive-id}/items/{item-id}/children (and /root/children) to list files, with @odata.nextLink pagination
- GET /drives/{drive-id}/items/{item-id}/content (302 to short-lived download URL) or @microsoft.graph.downloadUrl property to fetch file bytes
- driveItem.file and driveItem.hashes (quickXorHash, sha1Hash) for change-detection metadata -- NOT sha256Hash
- Application permissions: Files.Read.All (minimum), Sites.Read.All if reading SharePoint document libraries

**pitfalls**
- sha256Hash in the Graph hashes facet is documented as unsupported -- compute SHA-256 locally after download; do not build dedup logic around a Graph-provided sha256.
- Pre-authenticated 'tempauth' download URLs (@microsoft.graph.downloadUrl, the /content 302 target) are being retired by April 1, 2027; design the download call to be swappable for a direct Entra-token-authorized fetch.
- Folder listings page at 200 items by default; missing @odata.nextLink handling silently truncates large SharePoint/OneDrive folders.
- grantedTo/grantedToIdentities permission properties are being removed after a 4-year deprecation; use grantedToV2/grantedToIdentitiesV2 if the importer ever touches sharing permissions.
- drive/sharedWithMe endpoint was flagged deprecated in Microsoft tooling around Nov 2025 per secondary sources [uncertain] -- avoid depending on it for this importer regardless, since direct site/drive access is the intended path.

*As of: Microsoft Graph v1.0 REST API, pages last updated 2025-08 to 2026-10; msgraph-sdk (Python) 1.65.0 released 2026-10-22; tempauth retirement announced 2026-10, effective 2027-04-01*

**Sources**
- [driveItem resource type - Microsoft Graph v1.0](https://learn.microsoft.com/en-us/graph/api/resources/driveitem?view=graph-rest-1.0) (official-docs) -- "The driveItem resource represents a file, folder, or other item stored in a drive. All file system objects in OneDrive and SharePoint are returned as driveItem resources."
- [List the contents of a folder - Microsoft Graph v1.0](https://learn.microsoft.com/en-us/graph/api/driveitem-list-children?view=graph-rest-1.0) (official-docs) -- "Application | Files.Read.All | Files.ReadWrite.All, Sites.Read.All, Sites.ReadWrite.All ... GET /drives/{drive-id}/items/{item-id}/children"
- [Download driveItem content - Microsoft Graph v1.0](https://learn.microsoft.com/en-us/graph/api/driveitem-get-content?view=graph-rest-1.0) (official-docs) -- "Returns a 302 Found response redirecting to a preauthenticated download URL for the file ... Preauthenticated download URLs are valid for a limited time ... might expire within minutes."
- [hashes resource type - Microsoft Graph v1.0](https://learn.microsoft.com/en-us/graph/api/resources/hashes?view=graph-rest-1.0) (official-docs) -- "sha256Hash | String | This property isn't supported. Don't use. ... quickXorHash is the only value that is guaranteed to be available for both OneDrive for work or school and OneDrive for home."
- [Get access without a user - Microsoft Graph](https://learn.microsoft.com/en-us/graph/auth-v2-service) (official-docs) -- "scope=https%3A%2F%2Fgraph.microsoft.com%2F.default&client_secret=...&grant_type=client_credentials ... Specify the preconfigured permissions by passing https://graph.microsoft.com/.default"
- [Pre-authenticated (tempauth) URLs are retiring: move to Microsoft Entra ID tokens before April 1, 2027](https://devblogs.microsoft.com/microsoft365dev/pre-authenticated-tempauth-urls-are-retiring-move-to-microsoft-entra-id-tokens-before-april-1-2027/) (official-docs) -- "Pre-authenticated URLs, the self-issued tokens SharePoint embeds directly in a URL, commonly seen as the tempauth query parameter ... April 1, 2027 is the cutoff date."
- [Removal of Deprecated SharePoint & OneDrive Permission Resource Properties - Microsoft 365 Developer Blog](https://devblogs.microsoft.com/microsoft365dev/removal-of-deprecated-sharepoint-onedrive-permission-resource-properties/) (official-docs) -- "Use grantedToV2 instead of grantedTo ... Use grantedToIdentitiesV2 instead of grantedToIdentities ... following a four-year notice of deprecation."
- [msgraph-sdk · PyPI](https://pypi.org/project/msgraph-sdk/) (other) -- "Current Version: 1.65.0, Release Date: October 22, 2026 ... requires Python >=3.10 and explicitly supports Python 3.10, 3.11, 3.12, 3.13, and 3.14."

## Documentation sources

- [Azure OpenAI in Microsoft Foundry Models v1 API (API evolution / lifecycle)](https://learn.microsoft.com/en-us/azure/foundry/openai/api-version-lifecycle)
- [Azure OpenAI image and audio REST API reference (2024-10-21) - Microsoft Foundry](https://learn.microsoft.com/en-us/azure/foundry/openai/reference)
- [Microsoft Foundry REST Reference - Azure OpenAI - Embeddings](https://learn.microsoft.com/en-us/rest/api/microsoft-foundry/azureopenai/embeddings)
- [Generate embeddings with Azure OpenAI - Microsoft Foundry](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/embeddings)
- [How to use vision-enabled chat models - Microsoft Foundry](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/gpt-with-vision)
- [How to migrate to OpenAI Python v1.x (classic) - Microsoft Foundry (classic)](https://learn.microsoft.com/en-us/azure/foundry-classic/openai/how-to/migration)
- [Quickstart: Get started with Microsoft Foundry SDK - Microsoft Foundry | Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/quickstarts/get-started-code)
- [Get started with Microsoft Foundry SDKs and endpoints (classic) - Microsoft Foundry (classic) portal | Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry-classic/how-to/develop/sdk-overview?pivots=programming-language-python)
- [What's new in Document Intelligence - Foundry Tools | Microsoft Learn](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/whats-new?view=doc-intel-4.0.0)
- [Azure Document Intelligence Pricing (vendor pricing page, dynamically rendered)](https://azure.microsoft.com/en-us/pricing/details/ai-document-intelligence/)
- [What Is Azure Document Intelligence in Foundry Tools? - Foundry Tools | Microsoft Learn](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/overview?view=doc-intel-4.0.0)
- [Read model OCR data extraction - Document Intelligence - Foundry Tools | Microsoft Learn](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/prebuilt/read?view=doc-intel-4.0.0)
- [Migrate to v4.0. - Foundry Tools | Microsoft Learn (Document Intelligence migration guide)](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/versioning/migration-guide-overview)
- [Use Document Intelligence client library or REST API - Foundry Tools | Microsoft Learn](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/how-to-guides/use-sdk-rest-api?view=doc-intel-4.0.0)
- [azure-ai-documentintelligence · PyPI](https://pypi.org/project/azure-ai-documentintelligence/)
- [OpenAI API docs — Embeddings guide](https://developers.openai.com/api/docs/guides/embeddings)
- [OpenAI API docs — text-embedding-3-large model page](https://developers.openai.com/api/docs/models/text-embedding-3-large)
- [OpenAI API docs — Deprecations](https://developers.openai.com/api/docs/deprecations)
- [Azure AI Foundry model catalog — text-embedding-3-large](https://ai.azure.com/catalog/models/text-embedding-3-large)
- [Supported versions of PostgreSQL in Azure Database for PostgreSQL flexible server](https://learn.microsoft.com/en-us/azure/postgresql/configure-maintain/concepts-supported-versions)
- [Vector Search in Azure Database for PostgreSQL Flexible Server](https://learn.microsoft.com/en-us/azure/postgresql/extensions/how-to-use-pgvector)
- [Optimize Performance when Using pgvector in Azure Database for PostgreSQL Flexible Server](https://learn.microsoft.com/en-us/azure/postgresql/extensions/how-to-optimize-performance-pgvector)
- [Allow Extensions in Azure Database for PostgreSQL Flexible Server](https://learn.microsoft.com/en-us/azure/postgresql/extensions/how-to-allow-extensions)
- [Supported extensions versions in Azure Database for PostgreSQL - Flexible Server (by engine)](https://learn.microsoft.com/en-us/azure/postgresql/extensions/concepts-extensions-by-engine?pivots=postgresql-16)
- [Release notes for the CLI module for Azure Database for PostgreSQL flexible server](https://learn.microsoft.com/en-us/azure/postgresql/release-notes/release-notes-cli)
- [Release notes for the REST APIs for Azure Database for PostgreSQL flexible server](https://learn.microsoft.com/en-us/azure/postgresql/release-notes/release-notes-api)
- [pgvector/pgvector (GitHub README)](https://github.com/pgvector/pgvector)
- [pgvector CHANGELOG.md](https://raw.githubusercontent.com/pgvector/pgvector/master/CHANGELOG.md)
- [Vector Search in Azure Database for PostgreSQL Flexible Server - Microsoft Learn](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/how-to-use-pgvector)
- [PostgreSQL: Documentation: current: F.35. pg_trgm](https://www.postgresql.org/docs/current/pgtrgm.html)
- [PostgreSQL 18.0 Release Notes](https://www.postgresql.org/docs/release/18.0/)
- [PostgreSQL 18.2 Release Notes](https://www.postgresql.org/docs/release/18.2/)
- [List of Extensions and Modules by Name in Azure Database for PostgreSQL Flexible Server](https://learn.microsoft.com/en-us/azure/postgresql/extensions/concepts-extensions-versions)
- [Jobs in Azure Container Apps | Microsoft Learn](https://learn.microsoft.com/en-us/azure/container-apps/jobs)
- [az containerapp job | Microsoft Learn](https://learn.microsoft.com/en-us/cli/azure/containerapp/job?view=azure-cli-latest)
- [Microsoft.App/jobs - Bicep, ARM template & Terraform AzAPI reference | Microsoft Learn](https://learn.microsoft.com/en-us/azure/templates/microsoft.app/jobs)
- [Introduction to Azure Container Registry](https://learn.microsoft.com/en-us/azure/container-registry/container-registry-intro)
- [Azure Container Registry FAQ](https://learn.microsoft.com/en-us/azure/container-registry/container-registry-faq)
- [Transition from Docker Content Trust to Notary Project](https://learn.microsoft.com/en-us/azure/container-registry/container-registry-content-trust-deprecation)
- [Set Up Private Endpoint with Private Link for ACR](https://learn.microsoft.com/en-us/azure/container-registry/container-registry-private-endpoints)
- [Microsoft.ContainerRegistry/registries - all versions](https://learn.microsoft.com/en-us/azure/templates/microsoft.containerregistry/allversions)
- [Azure Key Vault Secrets client library for Python | Microsoft Learn](https://learn.microsoft.com/en-us/python/api/overview/azure/keyvault-secrets-readme?view=azure-python)
- [azure-keyvault-secrets CHANGELOG (Azure/azure-sdk-for-python)](https://github.com/Azure/azure-sdk-for-python/blob/main/sdk/keyvault/azure-keyvault-secrets/CHANGELOG.md)
- [Grant permission to applications to access an Azure key vault using Azure RBAC | Microsoft Learn](https://learn.microsoft.com/en-us/azure/key-vault/general/rbac-guide)
- [Managed identities in Azure Container Apps | Microsoft Learn](https://learn.microsoft.com/en-us/azure/container-apps/managed-identity)
- [Managed identities for Azure resources - overview](https://learn.microsoft.com/en-us/entra/identity/managed-identities-azure-resources/overview)
- [Azure Identity client library for Python](https://learn.microsoft.com/en-us/python/api/overview/azure/identity-readme?view=azure-python)
- [azure-identity · PyPI](https://pypi.org/project/azure-identity/)
- [Microsoft Entra Authentication in Azure Database for PostgreSQL Flexible Server](https://learn.microsoft.com/en-us/azure/postgresql/security/security-entra-concepts)
- [Managed Identities in Azure Database for PostgreSQL Flexible Server](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/security-managed-identity-overview)
- [Microsoft Graph REST API v1.0 endpoint reference](https://learn.microsoft.com/en-us/graph/api/overview?view=graph-rest-1.0)
- [Versioning, support, and breaking change policies for Microsoft Graph](https://learn.microsoft.com/en-us/graph/versioning-and-support)
- [Download driveItem content - Microsoft Graph v1.0](https://learn.microsoft.com/en-us/graph/api/driveitem-get-content?view=graph-rest-1.0)
- [hashes resource type - Microsoft Graph v1.0](https://learn.microsoft.com/en-us/graph/api/resources/hashes?view=graph-rest-1.0)
- [Get access without a user - Microsoft Graph](https://learn.microsoft.com/en-us/graph/auth-v2-service)
- [Install a Microsoft Graph SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation?tabs=python)
- [msgraph-sdk · PyPI](https://pypi.org/project/msgraph-sdk/)
- [What's new in Microsoft Graph](https://learn.microsoft.com/en-us/graph/whats-new-overview)
- [SharePoint sites and content API overview - Microsoft Graph](https://learn.microsoft.com/en-us/graph/sharepoint-concept-overview)
- [driveItem resource type - Microsoft Graph v1.0](https://learn.microsoft.com/en-us/graph/api/resources/driveitem?view=graph-rest-1.0)
- [driveItem: delta - Microsoft Graph v1.0](https://learn.microsoft.com/en-us/graph/api/driveitem-delta?view=graph-rest-1.0)
- [File resource type - Microsoft Graph v1.0](https://learn.microsoft.com/en-us/graph/api/resources/file?view=graph-rest-1.0)
- [Overview of Selected Permissions in OneDrive and SharePoint - Microsoft Graph](https://learn.microsoft.com/en-us/graph/permissions-selected-overview)
- [SharePoint Add-Ins and Azure ACS retirement FAQ](https://learn.microsoft.com/en-us/sharepoint/dev/sp-add-ins/add-ins-and-azure-acs-retirements-faq)
- [List the contents of a folder - Microsoft Graph v1.0](https://learn.microsoft.com/en-us/graph/api/driveitem-list-children?view=graph-rest-1.0)
- [Pre-authenticated (tempauth) URLs are retiring: move to Microsoft Entra ID tokens before April 1, 2027](https://devblogs.microsoft.com/microsoft365dev/pre-authenticated-tempauth-urls-are-retiring-move-to-microsoft-entra-id-tokens-before-april-1-2027/)
- [Removal of Deprecated SharePoint & OneDrive Permission Resource Properties - Microsoft 365 Developer Blog](https://devblogs.microsoft.com/microsoft365dev/removal-of-deprecated-sharepoint-onedrive-permission-resource-properties/)

Documentation items with no official source: Official documentation: Azure Container Apps; Official documentation: Bicep; Official documentation: Azure Blob Storage; Official documentation: FastAPI; Official documentation: SQLAlchemy 2.0; Official documentation: pydantic-settings; Official documentation: WhatsApp Business Platform / Cloud API; Official documentation: gunicorn; Official documentation: uvicorn.

## Academic literature

- **2D Matryoshka Training for Information Retrieval** (2025), cited 2x -- [link](https://doi.org/10.1145/3726302.3730330) / [PDF](https://dl.acm.org/doi/pdf/10.1145/3726302.3730330) _(via openalex)_
- **OCRVerse: Towards Holistic OCR in End-to-End Vision-Language Models** (2026), cited 0x -- [link](https://doi.org/10.48550/arxiv.2601.21639) / [PDF](https://arxiv.org/pdf/2601.21639) _(via openalex)_
- **Starbucks-v2: Improved Training for 2D Matryoshka Embeddings** (2024), cited 0x -- [link](https://doi.org/10.48550/arxiv.2410.13230) / [PDF](https://arxiv.org/pdf/2410.13230) _(via openalex)_
- **A Hybrid Architecture for Multi-Stage Claim Document Understanding: Combining Vision-Language Models and Machine Learning for Real-Time Processing** (2026) -- [link](https://arxiv.org/abs/2601.01897) / [PDF](https://arxiv.org/pdf/2601.01897v1) _(via arxiv)_
- **The Structured Output Benchmark: A Multi-Source Benchmark for Evaluating Structured Output Quality in Large Language Models** (2026) -- [link](https://arxiv.org/abs/2604.25359) / [PDF](https://arxiv.org/pdf/2604.25359v1) _(via arxiv)_
- **Geometric Structure Predicts Per-Example Neighborhood Loss Under PCA Truncation** (2026) -- [link](https://arxiv.org/abs/2610.17742) / [PDF](https://arxiv.org/pdf/2610.17742v1) _(via arxiv)_
- **Lost in OCR Translation? Vision-Based Approaches to Robust Document Retrieval** (2025) -- [link](https://arxiv.org/abs/2505.05666) / [PDF](https://arxiv.org/pdf/2505.05666v1) _(via arxiv)_
- **Multi-Stage Field Extraction of Financial Documents with OCR and Compact Vision-Language Models** (2025) -- [link](https://arxiv.org/abs/2510.23066) / [PDF](https://arxiv.org/pdf/2510.23066v1) _(via arxiv)_

## Prior art

- [pulumi/examples](https://github.com/pulumi/examples) -- 2582 stars, TypeScript, licence Apache-2.0. Infrastructure, containers, and serverless apps to AWS, Azure, GCP, and Kubernetes... all deployed with Pulumi
- [O365/python-o365](https://github.com/O365/python-o365) -- 1928 stars, Python, licence Apache-2.0. A simple python library to interact with Microsoft Graph and Office 365 API
- [vgrem/office365-rest-python-client](https://github.com/vgrem/office365-rest-python-client) -- 1729 stars, Python, licence MIT. Microsoft 365 & Microsoft Graph Library for Python

**Patterns worth reusing**

## Prior-art patterns worth reusing

**pulumi/examples** (Apache-2.0, TS) — Not directly applicable since our constraint is Bicep, not Pulumi; don't adopt the tool itself. Worth borrowing: the **preview-before-deploy pattern** (`make pr_preview` runs provider dry-runs on changed examples before real deploy) — mirrors our "scripted but not executed" cutover requirement; replicate as a Bicep `what-if` CI step. Also reusable: per-example Black/ESLint formatting gate in CI, and the Makefile `ensure`/`only_test` separation (setup vs. test) for the Bicep/ingest test pipeline.

**O365/python-o365** (Apache-2.0, Python) — Reuse the **pagination iterator** pattern ("request infinite items" via auto-following `@odata.nextLink`) for the SharePoint/OneDrive importer (acceptance criterion 10). Reuse their **automatic refresh-token handling** around MSAL rather than hand-rolling token refresh. Factory-based `ApiComponent` modularity is a reasonable shape for a Graph import module, but don't copy their full Account abstraction — it's mail/calendar-oriented and heavier than needed for a read-only file importer.

**vgrem/office365-rest-python-client** (MIT, Python) — Prefer their **`GraphClient`** (not `ClientContext`) since SharePoint/OneDrive-via-Graph is the scope here; MIT licence permits direct code reuse if needed, unlike the Apache repos above where only patterns should be borrowed (Apache is also copy-compatible but carries attribution/NOTICE obligations — still fine, just keep notices). Concretely reusable: fluent `.select()/.filter()/.expand()` deferred-execution query builder, typed `DriveItem` model for dedupe-by-hash logic. **Important technical fact, not just pattern**: SharePoint ACS app-only auth retired April 2026 and SAML retired May 2026 — use certificate, interactive, or device-code flow for Graph auth, not legacy app-only/SAML examples even if found elsewhere in that repo.

**Nothing to flag as a licence blocker** — all three repos (Apache-2.0, Apache-2.0, MIT) permit code reuse with attribution; no GPL/AGPL exposure.

_No repositories matched "FastAPI Azure OpenAI structured output JSON response_schema example repo"; retried as "fastapi azure openai"._
_No repositories matched "pgvector HNSW Azure PostgreSQL Flexible Server sample"; retried as "pgvector hnsw azure"._
_No repositories matched "Azure Container Apps Jobs Bicep deployment example"; retried as "azure container apps"._
_No repositories matched "Microsoft Graph SharePoint download files python sha256 dedupe"; retried as "microsoft graph sharepoint"._
_No repositories matched "storage provider abstraction interface google cloud storage azure blob python"; retried as "storage provider abstraction"._

## Open uncertainties

- Official documentation: Azure OpenAI Service: `current_version`
- Official documentation: Azure OpenAI Service: `pitfalls`
- Official documentation: Microsoft Foundry (Azure AI Foundry): `key_findings`
- Official documentation: Microsoft Foundry (Azure AI Foundry): `pitfalls`
- Official documentation: Azure AI Document Intelligence: `key_findings`
- Official documentation: Azure AI Document Intelligence: `pitfalls`
- Official documentation: text-embedding-3-large: `key_findings`
- Official documentation: text-embedding-3-large: `recommendations`
- Official documentation: text-embedding-3-large: `pitfalls`
- Official documentation: pgvector: `key_findings`
- Official documentation: pgvector: `pitfalls`
- Official documentation: pg_trgm: `pitfalls`
- Official documentation: Azure Container Apps Jobs: `current_version`
- Official documentation: Azure Container Apps Jobs: `api_surface`
- Official documentation: Microsoft Graph API: `key_findings`
- Official documentation: Microsoft Graph API: `pitfalls`
- Official documentation: SharePoint: `current_version`
- Official documentation: SharePoint: `api_surface`
- Official documentation: OneDrive: `pitfalls`

## Not researched

- docs-azure-container-apps: The model reply was not valid JSON: Expected ',' or '}' after property value in JSON at position 996 (line 2 column 995)
- docs-bicep: Field "pitfalls" contains [uncertain] but is not listed in the "uncertain" array.
- docs-azure-blob-storage: claude-code: The AI provider stopped with an error (it exited with code 1).
- docs-fastapi: claude-code: The AI provider stopped with an error (it exited with code 1).
- docs-sqlalchemy-2-0: claude-code: The AI provider stopped with an error (it exited with code 1).
- docs-pydantic-settings: claude-code: The AI provider stopped with an error (it exited with code 1).
- docs-whatsapp-business-platform-cloud-api: claude-code: The AI provider stopped with an error (it exited with code 1).
- docs-gunicorn: claude-code: The AI provider stopped with an error (it exited with code 1).
- docs-uvicorn: claude-code: The AI provider stopped with an error (it exited with code 1).
- azure-openai-foundry-models: claude-code: The AI provider stopped with an error (it exited with code 1).
- azure-embeddings-768: claude-code: The AI provider stopped with an error (it exited with code 1).
- azure-document-intelligence-ocr: claude-code: The AI provider stopped with an error (it exited with code 1).
- azure-postgres-pgvector: claude-code: The AI provider stopped with an error (it exited with code 1).
- container-apps-jobs-acr-bicep: claude-code: The AI provider stopped with an error (it exited with code 1).
- keyvault-managed-identity-config: claude-code: The AI provider stopped with an error (it exited with code 1).
- graph-sharepoint-importer: claude-code: The AI provider stopped with an error (it exited with code 1).
- gcs-sql-to-azure-migration: claude-code: The AI provider stopped with an error (it exited with code 1).
