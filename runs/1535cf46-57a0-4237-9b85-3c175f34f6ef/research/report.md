# Research report -- Migrate a FastAPI retrieval bot from GCP/Vertex to Azure: OpenAI/Foundry models, Postgres+pgvector, Container Apps, Graph import

Generated 2026-11-11T06:27:50.926Z by OSA. Researched by claude-code using its built-in web search. Time range: last 2 years (prioritise 2025-2026 current Azure offerings).
Values marked [uncertain] could not be verified from a source the agent opened; they are repeated under *Open uncertainties*.

## Findings

### Official documentation: Azure OpenAI Service
*Find the OFFICIAL documentation for "Azure OpenAI Service": its current stable version, how it is installed or enabled, the API surface this build will use, and any breaking changes or pitfalls in the last 2 years (prioritise 2025-2026 current Azure offerings).*

Azure OpenAI Service is now documented as 'Azure OpenAI in Microsoft Foundry Models,' reachable via a classic or new Foundry portal, and offers two parallel API surfaces: dated REST `api-version=YYYY-MM-DD` versions and a new unified `v1` API that reached GA in August 2025 and removes the need to track monthly api-versions. For this build, the relevant surface is resource/model deployment (via `az cognitiveservices account create`/`deployment create` or Bicep), the embeddings endpoint (supports a `dimensions` parameter on text-embedding-3-and-later models, needed to force 768-dim output), and chat completions for text and vision (OCR) calls. The main pitfalls are the ongoing Foundry rebrand changing doc URLs/resource types, and the v1-vs-dated-API split requiring a deliberate choice of client pattern.

**Key findings**
- Azure OpenAI Service is documented as 'Azure OpenAI in Microsoft Foundry Models,' with docs split across a new Foundry portal (/azure/foundry/openai/...) and a Foundry (classic) portal (/azure/foundry-classic/openai/...), per pages dated 2026-05 through 2026-09.
- A unified v1 API reached GA starting August 2025: base_url `https://{resource}.openai.azure.com/openai/v1/`, no `api-version` query param needed for GA features, use the plain `OpenAI()` client (not `AzureOpenAI()`), and Microsoft Entra ID tokens auto-refresh without a separate Azure client.
- Dated REST versioning (`?api-version=YYYY-MM-DD`) still works in parallel: latest GA data-plane image/audio release is `2024-10-21`; preview chain runs through `2025-04-01-preview` then v1-preview/v1; control-plane (resource/deployment management) latest GA is `2025-06-01`, latest preview `2025-07-01-preview`.
- Embeddings endpoint: `POST {endpoint}/openai/v1/embeddings` (or `/openai/deployments/{deployment-id}/embeddings?api-version=...` on dated versions). Request body fields: `model`, `input` (required), optional `dimensions` (integer, min 1), `encoding_format` (`float`|`base64`), `user`.
- `dimensions` is documented as supported only on `text-embedding-3` and later models (not `text-embedding-ada-002`); default output is 3072-dim for text-embedding-3-large / 1536-dim for text-embedding-3-small, and the parameter is how a smaller vector such as 768 is requested. [uncertain: the exact minimum dated api-version that first exposed `dimensions` was not confirmed from a primary docs page opened in this research]
- Resource provisioning: create a resource via Azure Portal, `az cognitiveservices account create --kind OpenAI --sku s0`, `New-AzCognitiveServicesAccount -Type OpenAI`, or ARM/Bicep (`Microsoft.CognitiveServices/accounts`); then deploy a model with `az cognitiveservices account deployment create --model-name ... --model-format OpenAI --sku-name Standard|GlobalStandard|GlobalBatch|ProvisionedManaged`, producing a separate deployment name used in API calls instead of the raw model name.
- Chat, completions, and embeddings operations live under the REST reference at `/rest/api/microsoft-foundry/azureopenai/*`, which is a separate reference page from the image/audio-only data-plane reference.

**Recommendations**
- Use the v1 API (base_url .../openai/v1/, plain OpenAI() client) for new adapter code to avoid monthly api-version churn; only pin a dated api-version if a needed capability isn't yet GA under v1.
- Deploy text-embedding-3-small or text-embedding-3-large and pass dimensions=768 explicitly on every embeddings call to match the existing Vector(768) pgvector column; never rely on the model's default dimensionality.
- Confirm the installed openai Python SDK version supports the dimensions keyword argument before wiring the embeddings adapter.
- Keep 'deployment name' (not base model name) as the configurable value in the swappable AI adapter/pydantic-settings config, since Azure always calls models by deployment name.
- Pick once whether to provision the classic 'Azure OpenAI resource' or the newer 'Foundry resource' type and keep Bicep/IaC consistent; don't let the portal's upgrade prompt change the resource type mid-project.
- For the OCR A/B gate, use a generally-available vision-capable chat-completions model rather than any limited-access/registration-gated model, to avoid access-approval delays blocking the comparison.
- Re-check region, model, and quota availability before finalizing Bicep parameters, since embedding and vision model availability is region- and SKU-dependent.

**current version:** Dual versioning: dated REST api-version=YYYY-MM-DD (latest GA data-plane 2024-10-21 for image/audio; control-plane GA 2025-06-01) plus the new unified v1 API (GA since Aug 2025, api-version=v1)

**api surface**
- POST {endpoint}/openai/v1/embeddings with body {model, input, dimensions=768, encoding_format}
- POST {endpoint}/openai/deployments/{deployment-id}/chat/completions?api-version=... for text and vision (image_url content parts) used in retrieval answers and OCR comparison
- az cognitiveservices account create --kind OpenAI --sku s0 (or Microsoft.CognitiveServices/accounts in Bicep) for resource provisioning
- az cognitiveservices account deployment create --model-name ... --model-format OpenAI --sku-name Standard|GlobalStandard for model deployment (embedding + chat/vision models)
- Auth via api-key header or Microsoft Entra ID bearer token (DefaultAzureCredential + get_bearer_token_provider, scope https://ai.azure.com/.default or https://cognitiveservices.azure.com/.default)
- OpenAI() Python client with base_url=https://{resource}.openai.azure.com/openai/v1/ as the v1 API alternative to the dated-version AzureOpenAI() client

**pitfalls**
- Ongoing Foundry rebrand: docs and portal are split into 'new Foundry portal' and 'Foundry (classic) portal' with different URL trees; mixing instructions from both can lead to stale steps.
- v1 API GA (Aug 2025) changes the client pattern (OpenAI() + base_url .../openai/v1/, no api-version) versus the older AzureOpenAI()+dated-api-version pattern; mixing the two patterns in one codebase is a common source of confusion.
- A documented breaking change between 2024-03-01-preview and 2024-04-01-preview removed the 'Enhancements' parameters, impacting the gpt-4 vision-preview model family — relevant if the OCR path uses an older vision-preview deployment.
- The 2025-04-01-preview spec uses OpenAPI 3.1, which is a known issue for full support in Azure API Management if the build fronts Azure OpenAI with APIM.
- The Azure portal now prompts an 'Azure OpenAI resource' -> 'Foundry resource' upgrade; accepting it mid-project can change behavior/endpoint handling, so Bicep/IaC should fix one resource type deliberately.
- Azure OpenAI always requires calling by deployment name, not the underlying model name, which differs from direct OpenAI API usage and is easy to miss when porting existing calling code.

*As of: Docs read Nov 2026; v1 API GA since Aug 2025; dated GA data-plane 2024-10-21, control-plane GA 2025-06-01*

**Sources**
- [What's new in Azure OpenAI in Microsoft Foundry Models? (classic)](https://learn.microsoft.com/en-us/azure/ai-services/openai/whats-new) (official-docs) -- "Starting in August 2025, you can opt in to the next generation v1 Azure OpenAI APIs which add support for: Ongoing access to the latest features with no need to specify new api-version's each month."
- [Azure OpenAI image and audio REST API reference (2024-10-21) - Microsoft Foundry](https://learn.microsoft.com/en-us/azure/ai-services/openai/reference) (official-docs) -- "The service APIs are versioned using the api-version query parameter. All versions follow the YYYY-MM-DD date structure."
- [Azure OpenAI in Microsoft Foundry Models v1 API](https://learn.microsoft.com/en-us/azure/ai-services/openai/api-version-lifecycle) (official-docs) -- "The v1 API simplifies authentication, removes the need for dated api-version parameters, and supports cross-provider model calls."
- [Microsoft Foundry REST Reference - Azure OpenAI - Embeddings](https://learn.microsoft.com/en-us/rest/api/microsoft-foundry/azureopenai/embeddings) (official-docs) -- "dimensions | integer | The number of dimensions the resulting output embeddings should have. Only supported in text-embedding-3 and later models. Constraints: min: 1"
- [How-to: Create and deploy an Azure OpenAI in Microsoft Foundry Models resource (classic)](https://learn.microsoft.com/en-us/azure/ai-services/openai/how-to/create-resource) (official-docs) -- "az cognitiveservices account create --name MyOpenAIResource --resource-group OAIResourceGroup --location eastus --kind OpenAI --sku s0 ..."


### Official documentation: Azure AI Foundry
*Find the OFFICIAL documentation for "Azure AI Foundry": its current stable version, how it is installed or enabled, the API surface this build will use, and any breaking changes or pitfalls in the last 2 years (prioritise 2025-2026 current Azure offerings).*

Azure AI Foundry was rebranded to "Microsoft Foundry" at Ignite 2025 (effective naming from Jan 2026); the new Foundry portal is GA, and official docs now live under learn.microsoft.com/azure/foundry/. For this build, Azure OpenAI chat/vision models are called through the new v1 GA REST surface (`{endpoint}/openai/v1/...`) using the plain `openai` Python SDK's `OpenAI()` client (not `AzureOpenAI()`) with a `base_url` ending in `/openai/v1/`, authenticated by API key or Microsoft Entra ID (`DefaultAzureCredential` + bearer token). Embeddings use `POST {endpoint}/openai/v1/embeddings` with a `dimensions` parameter that is only supported on `text-embedding-3-*` and later models — this is the mechanism to force a 768-dim vector to match the existing pgvector `Vector(768)` column. OCR for the A/B gate should use the Document Intelligence `prebuilt-read` model via `azure-ai-documentintelligence` (current stable 1.0.2, REST API `2024-11-30` GA), as a separate, auditable OCR engine distinct from GPT-4o vision chat completions.

**Key findings**
- Azure AI Foundry was renamed "Microsoft Foundry" at Microsoft Ignite (Nov 2025), with docs/portal using the new name as current as of 2026; the new Foundry portal is GA (learn.microsoft.com/azure/foundry/concepts/general-availability, dated 2026-08-14).
- Standalone Azure OpenAI resources are NOT supported in the new Foundry portal UI (use Foundry classic portal or a Foundry project) — but the v1 API itself works against either 'a Foundry resource or Azure OpenAI resource' per the API prerequisites.
- Azure OpenAI v1 GA API (opt-in since August 2025) removes dated `api-version` query params; use `from openai import OpenAI`, `base_url="https://YOUR-RESOURCE-NAME.openai.azure.com/openai/v1/"`, with `api_key` = static key or an Entra ID bearer-token provider (`get_bearer_token_provider(DefaultAzureCredential(), "https://ai.azure.com/.default")`).
- The older `AzureOpenAI()` client + monthly dated `api-version` (e.g. 2024-10-21, up to 2025-04-01-preview) still exists and is documented, but Microsoft recommends the v1 client for new code.
- Embeddings REST reference (`/openai/v1/embeddings`, API version `v1`): request supports `dimensions` (integer, min 1) 'Only supported in text-embedding-3 and later models'; max 8192 tokens per input, 300,000 tokens total per request.
- Document Intelligence Python SDK `azure-ai-documentintelligence` current stable release is 1.0.2 (released 2025-03-27 per PyPI); REST API `2024-11-30` is GA for Document Intelligence v4.0; `prebuilt-read` is the base OCR model, called via `client.begin_analyze_document("prebuilt-read", ...)`.
- `azure-ai-inference` package (ChatCompletionsClient/EmbeddingsClient) is the generic Foundry-models client for non-OpenAI catalog models; install with `pip install azure-ai-inference`; exact current version not stated on the fetched docs page [uncertain].
- Known breaking change: between API versions 2024-03-01-preview and 2024-04-01-preview, the GPT-4 `vision-preview` "enhancements" parameters were removed — any old Vision-grounding/enhancements-style code would break.
- Foundry is retiring the 'Workflows' preview feature on 2026-12-01 in favor of Microsoft Agent Framework — not directly used by this build but should not be adopted as a new dependency.
- Auth scopes differ slightly by surface: the v1 OpenAI API sample uses Entra scope `https://ai.azure.com/.default`; the embeddings REST reference lists OAuth2 scope `https://cognitiveservices.azure.com/.default` — both are valid Azure OpenAI/Cognitive Services scopes [uncertain] which one is canonical going forward.

**Recommendations**
- Use the plain `openai` Python package with the `OpenAI()` client (not `AzureOpenAI()`) and `base_url="https://<resource>.openai.azure.com/openai/v1/"` for chat/vision calls — this is the current GA pattern and avoids churn from monthly dated api-versions.
- For embeddings, explicitly pass `dimensions=768` on a `text-embedding-3-small` or `text-embedding-3-large` deployment to match the existing `Vector(768)` pgvector column unchanged; do not use `text-embedding-ada-002`, which does not support the `dimensions` param.
- Implement the OCR A/B gate (`prebuilt-read` via `azure-ai-documentintelligence` 1.0.2 / REST `2024-11-30`) as a distinct adapter from the Azure OpenAI vision chat path, since they are separate services with separate SLAs/pricing.
- Prefer Microsoft Entra ID (`DefaultAzureCredential`) over static API keys for the secrets/config adapter, per Foundry GA guidance that API keys 'don't provide the same role-based permission granularity.'
- Provision the Azure OpenAI resource as (or connected to) a Foundry project rather than a bare standalone Azure OpenAI resource, since standalone AOAI resources are out of GA scope for the new Foundry portal.
- Do not build any new dependency on Foundry 'Workflows' (slated for retirement 2026-12-01); keep the bot's own orchestration logic independent of that feature.
- Pin SDK versions explicitly in dependency files (`openai`, `azure-ai-documentintelligence==1.0.2`, `azure-identity`) since Foundry's API surface is still evolving rapidly (new preview headers, v1 GA features added 'rapidly').

**current version:** Microsoft Foundry portal: GA (renamed from Azure AI Foundry, Ignite 2025 / effective Jan 2026); Azure OpenAI v1 API: GA (opt-in since Aug 2025); azure-ai-documentintelligence: 1.0.2 (Mar 2025) / REST 2024-11-30 GA

**api surface**
- openai.OpenAI(base_url='https://<resource>.openai.azure.com/openai/v1/', api_key=...).chat.completions.create(model=..., messages=[...])
- openai.OpenAI(...).responses.create(model=..., input=...) — Responses API, recommended for new Azure OpenAI code
- POST {endpoint}/openai/v1/embeddings  body: {model, input, dimensions: 768}
- azure.identity.get_bearer_token_provider(DefaultAzureCredential(), 'https://ai.azure.com/.default') for Entra-based api_key
- azure.ai.documentintelligence.DocumentIntelligenceClient(endpoint, AzureKeyCredential(key)).begin_analyze_document('prebuilt-read', document_url_or_bytes)
- azure.ai.inference.ChatCompletionsClient / EmbeddingsClient (for non-OpenAI Foundry catalog models, if ever needed)

**pitfalls**
- Terminology/URL churn: 'Azure AI Foundry' → 'Microsoft Foundry' (Ignite 2025 / Jan 2026) — older blog posts, tutorials, and some doc paths (e.g. /azure/ai-foundry/...) may be stale redirects; verify against /azure/foundry/ paths.
- Standalone Azure OpenAI resources are excluded from the new Foundry portal's GA scope — provision via a Foundry project to get full GA support.
- v1 GA API uses `OpenAI()` not `AzureOpenAI()` and drops `api-version` entirely; mixing old `AzureOpenAI()` + dated api-version code with new v1 code in the same adapter will cause confusing auth/behavior differences.
- `dimensions` param for embeddings only works on text-embedding-3-small/large and later — will silently fail or be ignored/rejected on ada-002-class models.
- GPT-4 vision 'enhancements' parameters were removed in the 2024-04-01-preview API — do not port any old grounding/enhancements-based OCR logic expecting that parameter to exist.
- Foundry 'Workflows' preview feature is being retired 2026-12-01 — avoid building new orchestration on it.
- API key auth does not provide the same RBAC granularity as Entra ID per Foundry's own GA rollout guidance — plan secrets/config adapter accordingly for a school-owned, lower-ops-maturity deployment.

*As of: Docs fetched dated 2026-05-13 (api-version-lifecycle), 2026-08-14 (GA overview), 2026-09-01 (what's-new), 2026-07-09 (embeddings REST ref), 2025-03-27 (azure-ai-documentintelligence 1.0.2 release)*

**Sources**
- [Microsoft Foundry docs: What's new for August 2026](https://learn.microsoft.com/en-us/azure/foundry/whats-new-foundry) (official-docs) -- "Welcome! This article highlights key updates for Microsoft Foundry in August 2026."
- [Microsoft Foundry portal general availability overview](https://learn.microsoft.com/en-us/azure/foundry/concepts/general-availability) (official-docs) -- "Standalone Azure OpenAI resources: Not supported in the new Foundry portal... Foundry is retiring workflows on December 1, 2026."
- [Microsoft Foundry REST Reference - Azure OpenAI - Embeddings](https://learn.microsoft.com/en-us/rest/api/microsoft-foundry/azureopenai/embeddings) (official-docs) -- "dimensions | integer | The number of dimensions the resulting output embeddings should have. Only supported in text-embedding-3 and later models."
- [Azure OpenAI in Microsoft Foundry Models v1 API](https://learn.microsoft.com/en-us/azure/foundry/openai/api-version-lifecycle) (official-docs) -- "Starting in August 2025, you can opt in to the next generation v1 Azure OpenAI APIs... OpenAI() client is used instead of AzureOpenAI()."
- [Azure AI Inference client library README (azure-sdk-for-python)](https://github.com/Azure/azure-sdk-for-python/blob/main/sdk/ai/azure-ai-inference/README.md) (repo) -- "pip install azure-ai-inference ... client.complete(messages=[SystemMessage(...), UserMessage(...)])"
- [Quickstart: Document Intelligence client libraries - Foundry Tools](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/quickstarts/get-started-sdks-rest-api?view=doc-intel-4.0.0) (official-docs) -- "pip install azure-ai-documentintelligence==1.0.0 ... The current supported REST API version is 2024-11-30 (GA) for Document Intelligence v4.0."
- [azure-ai-documentintelligence · PyPI](https://pypi.org/project/azure-ai-documentintelligence/) (other) -- "The most recent stable release is version 1.0.2, released on March 27, 2025."


### Official documentation: text-embedding-3-large
*Find the OFFICIAL documentation for "text-embedding-3-large": its current stable version, how it is installed or enabled, the API surface this build will use, and any breaking changes or pitfalls in the last 2 years (prioritise 2025-2026 current Azure offerings).*

text-embedding-3-large is a single, undated OpenAI embedding model available on Azure OpenAI/Microsoft Foundry as a model deployment, callable via the OpenAI-compatible embeddings API. It defaults to 3072-dimensional output but supports a `dimensions` parameter to truncate to 768, which is what this build needs to match the existing pgvector Vector(768) column. Azure now offers a v1 GA API (`/openai/v1/embeddings`, no `api-version` needed) alongside the older dated api-version endpoints; both support the model. Hard limits to respect are 8,192 tokens per input, 2,048 inputs per request array, and a 300,000-token aggregate cap per request.

**Key findings**
- Default embedding size for text-embedding-3-large is 3072 dimensions; must pass dimensions=768 explicitly to get a 768-dim vector.
- Max input length is 8,192 tokens per text; max 2,048 inputs per array in one /embeddings request (Microsoft Learn, embeddings how-to, 2026-07-22).
- Azure OpenAI embeddings requests fail with HTTP 400 if the SUM of input tokens across all items in one request exceeds 300,000, even if each item is under 8,192 tokens.
- Azure's v1 GA API (/openai/v1/embeddings) is current since August 2025 and removes the need for a dated api-version query parameter; uses OpenAI()-style client with Entra ID bearer token or api-key.
- Model name used in the API call is the Azure deployment name (mapped to text-embedding-3-large), not the raw OpenAI model string.
- text-embedding-3-large supports the dimensions parameter to shorten output while retaining concept-representing properties (OpenAI embeddings guide).
- Per Microsoft's own model-retirements doc: 'Embeddings models (text-embedding-3-large, text-embedding-3-small, text-embedding-ada-002) have extended timelines and are handled differently from inference models' — no specific retirement date found for text-embedding-3-large as of 2026-07-24.
- Dimensions parameter accepts values from 1 up to 3072, and requires a sufficiently recent openai client SDK version to be supported in requests [uncertain].

**Recommendations**
- Always pass dimensions=768 explicitly in every embeddings.create call so output matches the existing Vector(768) pgvector column and HNSW index — never rely on the 3072 default.
- Use the Azure OpenAI v1 GA API (/openai/v1/embeddings) with Microsoft Entra ID (DefaultAzureCredential) auth per current Microsoft guidance, instead of older dated api-version endpoints.
- Chunk documents to <=8,192 tokens per input, keep request arrays <=2,048 items, and keep per-request aggregate tokens under 300,000 to avoid HTTP 400s.
- Pin the openai Python SDK to a current release before depending on the dimensions parameter.
- Before cutover, check the Azure Model Retirement Schedule for text-embedding-3-large since embeddings models follow a separate lifecycle from chat/vision models.

**current version:** text-embedding-3-large (single current model id, no dated snapshot variants); accessed via Azure OpenAI v1 GA API (/openai/v1/embeddings, no api-version param, GA since Aug 2025)

**api surface**
- client.embeddings.create(model=<azure-deployment-name>, input=text, dimensions=768) via openai Python SDK
- POST https://{resource}.openai.azure.com/openai/v1/embeddings (Azure v1 GA endpoint, no api-version query param)
- Auth: Microsoft Entra ID bearer token via DefaultAzureCredential + get_bearer_token_provider (recommended), or api-key header
- Response shape: response.data[0].embedding -> list[float] of length = requested dimensions (768)

**pitfalls**
- Omitting dimensions=768 returns 3072-dim vectors by default, breaking the fixed Vector(768) pgvector column/HNSW index.
- Aggregate token limit of 300,000 per request applies across all batched inputs combined, not just per-item 8,192 token limit.
- Max 2,048 inputs per array in a single embeddings request on Azure.
- Older openai 1.x SDK versions may not support the dimensions parameter; upgrade before use [uncertain].
- No explicit retirement date is published for text-embedding-3-large as of 2026-07-24; embeddings models use an 'extended' lifecycle separate from chat models, so standard 18-month GA timelines don't directly apply — recheck the retirement schedule before cutover.

*As of: Microsoft Learn Azure OpenAI/Foundry docs dated 2026-05-13 to 2026-07-24; OpenAI developers.openai.com embeddings guide accessed 2026-11-02 (undated page)*

**Sources**
- [Generate embeddings with Azure OpenAI - Microsoft Foundry | Microsoft Learn](https://learn.microsoft.com/en-us/azure/ai-foundry/openai/how-to/embeddings) (official-docs) -- "The maximum input length for the current embedding models is 8,192 tokens... Each /embeddings request has a 300,000-token aggregate limit across all inputs."
- [Foundry Models lifecycle and support policy - Microsoft Foundry | Microsoft Learn](https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/model-retirements) (official-docs) -- "Embeddings models (text-embedding-3-large, text-embedding-3-small, text-embedding-ada-002) have extended timelines and are handled differently from inference models."
- [Azure OpenAI in Microsoft Foundry Models v1 API - Microsoft Learn](https://learn.microsoft.com/en-us/azure/ai-foundry/openai/api-version-lifecycle) (official-docs) -- "Starting in August 2025, you can opt in to the next generation v1 Azure OpenAI APIs which add support for: Ongoing access to the latest features with no need to specify new api-version's each month."
- [Vector embeddings - OpenAI API documentation](https://developers.openai.com/api/docs/guides/embeddings) (official-docs) -- "By default, the length of the embedding vector is 3072 for text-embedding-3-large... pass in the dimensions parameter... removes some numbers from the end of the sequence without the embedding losing its concept-representing properties."


### Official documentation: Azure AI Document Intelligence
*Find the OFFICIAL documentation for "Azure AI Document Intelligence": its current stable version, how it is installed or enabled, the API surface this build will use, and any breaking changes or pitfalls in the last 2 years (prioritise 2025-2026 current Azure offerings).*

Azure AI Document Intelligence (formerly Form Recognizer) is GA at v4.0, using REST API version 2024-11-30 and Python SDK package `azure-ai-documentintelligence` v1.0.0 (latest patch 1.0.2). For this build's OCR A/B gate against Gemini vision, the relevant surface is the `prebuilt-read` model called via `DocumentIntelligenceClient.begin_analyze_document()`, returning pages/lines/words/paragraphs with confidence and polygon coordinates. The service is provisioned as a Cognitive Services 'Document Intelligence' resource (F0 free / S0 paid tier) and authenticated via API key or Entra ID (managed identity recommended for Container Apps).

**Key findings**
- Current GA: Document Intelligence v4.0, REST API version `2024-11-30`; Python SDK `azure-ai-documentintelligence` 1.0.0 is the GA release targeting this API version (per learn.microsoft.com sdk-overview-v4-0, docs dated 2026-08-15, last updated 2026-10-19).
- PyPI shows latest published patch as 1.0.2 (released Mar 27, 2025); install via `pip install azure-ai-documentintelligence==1.0.0` (or newer patch) per official docs.
- v4.0 client classes: `DocumentIntelligenceClient` and `DocumentIntelligenceAdministrationClient`, replacing v3.1's `DocumentAnalysisClient`/`DocumentModelAdministrationClient` from the old `azure-ai-formrecognizer` package.
- prebuilt-read (OCR) supports PDF, JPEG/JPG, PNG, BMP, TIFF, HEIF, plus Word/Excel/PowerPoint/HTML (Office formats added in v4.0, embedded images in Office/HTML not supported).
- Limits: up to 2,000 pages for PDF/TIFF (free F0 tier only processes first 2 pages); file size 500 MB on paid S0, 4 MB on free F0; image dimensions 50x50 to 10000x10000 px; min text height ~12px at 1024x768 (~8pt @150dpi).
- Searchable-PDF output (`?output=pdf`) was added with the 2024-11-30 GA release, supported only by `prebuilt-read`, at no extra cost.
- Auth: API key via `AzureKeyCredential`, or Entra ID via `DefaultAzureCredential` — but Entra ID auth requires a custom subdomain endpoint; plain regional endpoints don't support it.
- EOL schedule: preview API versions (2024-07-31-preview, 2024-02-29-preview, 2023-10-31-preview) reach end of support 2026-06-30; REST API v2.1 EOS 2027-09-15; v3.0 (2022-08-31) EOS 2029-03-30 — build should target 2024-11-30 GA, not a preview version.
- Historical breaking change (2023-07-31, v3.0→v3.1): `boundingBox` field renamed to `polygon` across analyze results — relevant only if comparing against very old code/output samples.
- Migrating from v3.1 SDK to v4.0 SDK requires updating client class names and import paths; official per-language migration guides exist on the azure-sdk-for-python GitHub repo (not yet opened directly).

**Recommendations**
- Pin the build to API version `2024-11-30` (GA) and SDK `azure-ai-documentintelligence>=1.0.0,<2` — do not use any `-preview` API version given the 2026-06-30 preview sunset.
- Use `prebuilt-read` for the OCR A/B gate (text/lines/words/paragraphs with confidence) since it's the right-fit model for scanned past-paper OCR, not `prebuilt-layout` (which adds tables/selection marks not needed here).
- Provision the Document Intelligence resource with a custom subdomain and use `DefaultAzureCredential` (managed identity) from Container Apps rather than an API key, per Microsoft's own security guidance; keep any key in Key Vault only as fallback.
- Account for the 500MB/4MB and 2000-page limits when batching scanned past-papers; confirm pricing tier is S0 (paid), not F0, before running real volume tests.
- When writing the OCR A/B gate report, extract comparable fields: `result.paragraphs[].content`, `result.pages[].lines[].content`, and `confidence` per word — these map cleanly to text-only comparison against Gemini OCR output.
- Read the official Python SDK migration guide on GitHub before writing adapter code, since this research did not fetch it directly (see uncertain).

**current version:** Document Intelligence service v4.0 GA (REST API 2024-11-30); Python SDK azure-ai-documentintelligence 1.0.0 GA (latest PyPI patch 1.0.2, Mar 2025)

**api surface**
- pip install azure-ai-documentintelligence==1.0.0 (or 1.0.x)
- from azure.ai.documentintelligence import DocumentIntelligenceClient
- from azure.identity import DefaultAzureCredential (managed identity on Container Apps) or azure.core.credentials.AzureKeyCredential
- client = DocumentIntelligenceClient(endpoint, credential) — endpoint must be a custom-subdomain Cognitive Services endpoint for Entra ID auth
- poller = client.begin_analyze_document('prebuilt-read', body=<file bytes/stream>); result = poller.result()
- result.paragraphs[].content, result.pages[].lines[].content, result.pages[].words[].content/.confidence
- Optional 'pages' query/parameter to restrict analysis to a page range for large multi-page PDFs

**pitfalls**
- Package/class rename on v3.1→v4.0 SDK upgrade: azure-ai-formrecognizer's DocumentAnalysisClient is replaced by azure-ai-documentintelligence's DocumentIntelligenceClient — do not mix the two packages.
- Preview API versions (2024-07-31-preview, 2024-02-29-preview, 2023-10-31-preview) sunset 2026-06-30 — any code pinned to a preview version will break; pin to 2024-11-30 GA.
- Entra ID / managed identity auth fails on plain regional endpoints; a custom subdomain is required.
- Free tier (F0) silently truncates PDFs/TIFFs to the first 2 pages and caps file size at 4MB — easy to misdiagnose as an OCR quality bug.
- Office (DOCX/XLSX/PPTX) and HTML inputs to prebuilt-read return words/paragraphs without bounding boxes and drop embedded images — not relevant for scanned past-papers but worth knowing if any source docs are Office files.
- Historical (2023-07-31) breaking rename: boundingBox → polygon in analyze results — only matters if comparing against pre-2023 sample output.
- Custom-trained models (not used in this build) expire and are tied to the API version they were trained on — not applicable since this build only uses the prebuilt-read model.

*As of: Docs pages last updated 2026-10-19 (ms.date 2026-08-15); PyPI package page checked 2026-11-02*

**Sources**
- [Read model OCR data extraction - Document Intelligence - Foundry Tools | Microsoft Learn](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/prebuilt/read?view=doc-intel-4.0.0) (official-docs) -- "Document Intelligence v4.0: 2024-11-30 (GA) supports ... Read OCR model ... Model ID: prebuilt-read ... up to 2,000 pages can be processed ... file size ... 500 MB for the paid (S0) tier and 4 MB for the free (F0) tier."
- [Document Intelligence SDK target REST API v4.0 - Foundry Tools | Microsoft Learn](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/versioning/sdk-overview-v4-0?view=doc-intel-4.0.0) (official-docs) -- "Python → 1.0.0 (GA) | PyPI | 2024-11-30 (GA) ... pip install azure-ai-documentintelligence==1.0.0 ... DocumentIntelligenceClient DocumentIntelligenceAdministrationClient"
- [Migrate to v4.0 - Foundry Tools | Microsoft Learn](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/versioning/migration-guide-overview) (official-docs) -- "Document Intelligence REST preview API versions (2024-07-31-preview, 2024-02-29-preview, 2023-10-31-preview) reach end of support on June 30, 2026 ... REST API v2.1 reaches end of support on September 15, 2027 ... v3.0 ... March 30, 2029."
- [azure-ai-documentintelligence · PyPI](https://pypi.org/project/azure-ai-documentintelligence/) (other) -- "Latest Version: 1.0.2 (Released Mar 27, 2025) ... pip install azure-ai-documentintelligence ... poller = client.begin_analyze_document("prebuilt-layout", body=f)"


### Official documentation: Azure Database for PostgreSQL Flexible Server
*Find the OFFICIAL documentation for "Azure Database for PostgreSQL Flexible Server": its current stable version, how it is installed or enabled, the API surface this build will use, and any breaking changes or pitfalls in the last 2 years (prioritise 2025-2026 current Azure offerings).*

Azure Database for PostgreSQL Flexible Server is the managed Postgres service this build will use for storage + pgvector retrieval. Current stable engine is PostgreSQL 18 (minor 18.6) for new servers, with 17.11/16.15/15.19/14.24 also fully supported; pgvector ships as the `vector` extension and must first be allow-listed via the `azure.extensions` server parameter before `CREATE EXTENSION vector;` works. HNSW indexing syntax (`CREATE INDEX ... USING hnsw (col vector_cosine_ops) WITH (m=16, ef_construction=64)`), the `vector(768)` column type, and `pg_trgm` for keyword search are all supported unchanged from upstream Postgres, with the key platform-specific pitfall being the 2000-dimension index cap (not relevant at 768) and the extension allow-list step. Provisioning for Bicep/`az deployment` uses resource type `Microsoft.DBforPostgreSQL/flexibleServers`, with current stable apiVersion `2025-08-01` (also `2025-01-01-preview`).

**Key findings**
- Current PostgreSQL major versions on Flexible Server: 18 (18.6, default for new servers), 17 (17.11), 16 (16.15), 15 (15.19), 14 (14.24); 13/12/11 are in Extended Support. [as of docs dated 2026-08-26]
- pgvector is installed as extension name `vector` (not `pgvector`) — must use that exact name both in the `azure.extensions` allow-list and in `CREATE EXTENSION vector;`.
- Two-step enable: (1) `az postgres flexible-server parameter set --name azure.extensions --value vector` (or Portal > Parameters), then (2) `CREATE EXTENSION vector;` per database — repeat per DB.
- pg_trgm is supported across PG 11–18 (extension version 1.4–1.6) and follows the same allow-list-then-CREATE-EXTENSION pattern; creating it requires the `azure_pg_admin` role or you get a permission-denied error. [uncertain: restart requirement for azure.extensions changes]
- Supported vector index types: IVFFlat, HNSW, and Azure-specific DiskANN (DiskANN is Azure Flexible Server-only, not in vanilla pgvector).
- HNSW CREATE INDEX syntax is unchanged from upstream pgvector: `CREATE INDEX ... USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);`; query-time tuning via `SET hnsw.ef_search = N;` (default 40).
- Hard limit: a vector column can only be indexed (ivfflat/hnsw) up to 2000 dimensions — irrelevant at 768 dims but a documented ceiling to be aware of.
- pgvector version on Azure has advanced through 0.8.0 (May 2025) to 0.8.2, which stabilizes parallel HNSW index builds and fixes correctness issues — relevant if the build builds HNSW indexes concurrently/in parallel. [uncertain: exact current default version per region/PG major — not independently confirmed beyond search summary]
- Bicep/ARM resource type is `Microsoft.DBforPostgreSQL/flexibleServers`; stable apiVersion `2025-08-01` exists alongside preview `2025-01-01-preview`. [uncertain: which apiVersion is the officially recommended/non-preview latest at time of writing — page content was too large to fully verify server-side]
- DiskANN index type requires Azure Flexible Server specifically (not available in open-source pgvector) — not needed here since HNSW is the locked choice, but worth knowing it's an Azure-only alternative.

**Recommendations**
- Use `vector(768)` column type and HNSW index with `vector_cosine_ops` (or whichever distance op matches current GCP/pgvector behavior) — syntax is identical to self-hosted pgvector, so no query/index code changes are needed beyond the connection string and provider.
- Add a provisioning/setup step (Bicep deployment script or post-deploy az cli call) that allow-lists `vector,pg_trgm` via `azure.extensions` before running `CREATE EXTENSION vector; CREATE EXTENSION pg_trgm;` — this is Azure-specific and has no equivalent in Cloud SQL, so don't skip it in the Bicep/runbook.
- Pin or verify the PostgreSQL major version used in Bicep (`properties.version`) matches what Cloud SQL ran, to avoid subtle SQL dialect differences; PG 16 or 17 are safe, well-supported choices if version parity with GCP isn't strict.
- When writing the Bicep template, use apiVersion `2025-08-01` (non-preview) for `Microsoft.DBforPostgreSQL/flexibleServers` unless a feature specifically requires the `2025-01-01-preview` surface; avoid preview APIs for a production/ownership-handoff build per the acceptance criteria's stability intent.
- Grant the app's connection role `azure_pg_admin` (or run the CREATE EXTENSION steps as the admin login) since pg_trgm/vector extension creation fails with permission-denied otherwise — budget this into the Bicep/db-init script.
- Do not assume `CREATE EXTENSION` alone works as on self-hosted Postgres — the allow-list step is the most common Azure-specific pitfall and should be an explicit, testable step in the migration scripts/runbook.

**current version:** PostgreSQL engine 18 (minor 18.6) default for new Flexible Server instances; pgvector extension ~0.8.x on Azure [uncertain]; Bicep resource apiVersion 2025-08-01 [uncertain]

**api surface**
- az postgres flexible-server create / parameter set (CLI provisioning and extension allow-listing)
- Bicep resource Microsoft.DBforPostgreSQL/flexibleServers (and /databases, /configurations sub-resources) for `az deployment`
- SQL: CREATE EXTENSION vector; CREATE EXTENSION pg_trgm;
- SQL: CREATE TABLE ... embedding vector(768)
- SQL: CREATE INDEX ... USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)
- SQL: SET hnsw.ef_search = N; (query-time tuning)
- Distance operators <->, <#>, <=> and functions cosine_distance/l2_distance/inner_product used by SQLAlchemy 2.0 queries

**pitfalls**
- CREATE EXTENSION vector/pg_trgm fails until the extension is added to the server-level azure.extensions allow-list first — a step with no equivalent on GCP Cloud SQL.
- Extension creation requires the azure_pg_admin role; a non-privileged app connection role gets permission-denied.
- Vector columns can't be indexed above 2000 dimensions (not a concern at 768, but a hard platform ceiling if embedding model changes later).
- pgvector on Azure has moved through 0.8.0 (May 2025) to 0.8.2 for parallel HNSW build stability — older pinned pgvector versions in Docker/app code should not be assumed; the server-side version is Azure-managed, not app-controlled.
- DiskANN is an Azure-only index type (not in upstream pgvector) — don't accidentally introduce it expecting portability back to self-hosted/GCP Postgres.
- Bicep apiVersion drift: preview API versions (e.g. 2025-01-01-preview) exist alongside stable ones; pick the stable 2025-08-01 (or later stable) to avoid relying on preview-only behavior in a handoff build.

*As of: Docs dated 2026-07-10 to 2026-08-27 (pgvector/extensions pages) and 2026-10-20 (Bicep template reference); PostgreSQL 18.6 is current default*

**Sources**
- [Supported versions of PostgreSQL in Azure Database for PostgreSQL flexible server](https://learn.microsoft.com/en-us/azure/postgresql/configure-maintain/concepts-supported-versions) (official-docs) -- "The current minor release is 18.6... New servers are created with this minor version."
- [Optimize Performance when Using pgvector in Azure Database for PostgreSQL Flexible Server](https://learn.microsoft.com/en-us/azure/postgresql/extensions/how-to-optimize-performance-pgvector) (official-docs) -- "You can only index a column that has up to 2000 dimensions... CREATE INDEX t_test_hnsw_l2_idx ON t_test USING hnsw (embedding vector_l2_ops) WITH (m = 16, ef_construction = 64);"
- [Vector Search in Azure Database for PostgreSQL Flexible Server](https://learn.microsoft.com/en-us/azure/postgresql/extensions/how-to-use-pgvector) (official-docs) -- "the name of the binary and the extension itself is simply vector. Take that name into consideration, because it's the name you must use to allowlist it or to create it on any database via the CREATE EXTENSION command."
- [Allow Extensions in Azure Database for PostgreSQL Flexible Server](https://learn.microsoft.com/en-us/azure/postgresql/extensions/how-to-allow-extensions) (official-docs) -- "az postgres flexible-server parameter set --resource-group <resource_group> --server-name <server> --name azure.extensions --value "<extension_name>,<extension_name>""
- [Microsoft.DBforPostgreSQL/flexibleServers - Bicep, ARM template & Terraform AzAPI reference](https://learn.microsoft.com/en-us/azure/templates/microsoft.dbforpostgresql/flexibleservers) (official-docs) -- "API version latest ... updated_at: 2026-10-20"


### Official documentation: pgvector
*Find the OFFICIAL documentation for "pgvector": its current stable version, how it is installed or enabled, the API surface this build will use, and any breaking changes or pitfalls in the last 2 years (prioritise 2025-2026 current Azure offerings).*

pgvector is the open-source Postgres extension providing a `vector` type plus `ivfflat`/`hnsw` approximate-nearest-neighbor indexes; this build keeps using it unchanged after the Azure move. On Azure Database for PostgreSQL Flexible Server, the extension is named `vector` (not `pgvector`), must be allowlisted via the `azure.extensions` server parameter, then enabled per-database with `CREATE EXTENSION vector;`. As of the Microsoft Learn extensions-versions page (dated 2026-07-10), Azure ships pgvector 0.8.2 for PostgreSQL 13-18 (0.7.0 for PG12, 0.5.1 for PG11), while the upstream pgvector project's latest tagged release is 0.8.7 (2026-10-01) -- Azure trails upstream by several patch releases. The API surface the build needs (vector(768) column, HNSW index, `<->`/`<=>` operators, `l2_distance`/`cosine_distance` functions) has been stable since 0.7.0 and required no breaking changes in the 2024-2026 window; the one forward-looking risk is the unreleased 0.9.0 line, which per the project's changelog plans to drop PostgreSQL 13/14 support.

**Key findings**
- Azure Database for PostgreSQL Flexible Server currently ships pgvector (extension name 'vector') version 0.8.2 for PG 13-18, 0.7.0 for PG12, 0.5.1 for PG11, per learn.microsoft.com/azure/postgresql/extensions/concepts-extensions-versions (ms.date 2026-07-10).
- Upstream pgvector's latest tagged release on GitHub is 0.8.7, dated 2026-10-01; prior 0.8.x releases span 0.8.0 (2024-10-30) through 0.8.6 (2026-07-29).
- Azure Release Notes record GA of 'Pgvector 0.5.1' (Nov 2023), 'version 0.6.0' (Mar 2024), 'Pgvector 0.7.0' (Jul 2024), and 'Pgvector 0.8.0 extension' (May 2025) -- the extensions-versions table shows it has since advanced to 0.8.2.
- On Azure, the binary/extension identifier is literally `vector`, not `pgvector`; it must first be added to the `azure.extensions` allowlist (Portal Parameters blade, or `az postgres flexible-server parameter set --name azure.extensions --value vector,...`) before `CREATE EXTENSION vector;` succeeds.
- pgvector supports six operators: `<->` (L2/Euclidean), `<#>` (negative inner product), `<=>` (cosine), `<+>` (L1), plus `<~>` (Hamming) and `<%>` (Jaccard) for binary vectors; and functions `l2_distance`, `cosine_distance`, `inner_product`, `l1_distance`, `vector_dims`, `vector_norms`.
- Two index types are available: HNSW (multilayer graph, slower build, better query recall/latency) and IVFFlat (faster build, lower query performance) -- this build should use HNSW to match the existing Vector(768)+HNSW design.
- Standard `vector` columns support up to 16,000 dimensions (half-precision `halfvec` also up to 16,000 dims at 2 bytes/element; binary vectors up to 64,000 dims; sparse vectors up to 16,000 non-zero elements) -- 768 dims is well within limits.
- pgvector's CHANGELOG lists an unreleased 0.9.0 line adding asynchronous I/O for HNSW indexes and dropping support for PostgreSQL 13 and 14 [uncertain]; several 0.7.4/0.8.x releases fixed HNSW vacuum and index-build bugs, none of which were flagged as breaking for the `<->`/`<=>` query API.

**Recommendations**
- Keep the existing SQLAlchemy 2.0 model unchanged: `Vector(768)` column type with a HNSW index on cosine distance (`vector_cosine_ops`), since both the upstream API and Azure's 0.8.2 build support this without modification.
- In the Bicep/IaC provisioning step, explicitly set the `azure.extensions` server parameter to include `vector` (and `pg_trgm`) before attempting `CREATE EXTENSION vector;` -- omitting the allowlist step is the most common failure mode on Azure Flexible Server.
- Pin application-level expectations to pgvector 0.8.x semantics (current Azure-supported version is 0.8.2); do not rely on any upstream 0.8.7-only or 0.9.0-only behavior (e.g., async HNSW I/O) until Azure's extensions-versions page shows that version available.
- If a future PostgreSQL major-version upgrade is planned, verify PG13/14 compatibility against pgvector before upgrading past 0.8.x, since the unreleased 0.9.0 line is slated to drop PG13/14 support.
- Use `ORDER BY embedding <=> query_vector LIMIT k` (cosine) for the retrieval callable to match the existing Vertex-era cosine-similarity ranking semantics; confirm HNSW `ef_search` is tuned the same as the current GCP deployment for parity in the before/after top-k comparison.

**current version:** Upstream pgvector: 0.8.7 (2026-10-01), with 0.9.0 unreleased; Azure Database for PostgreSQL Flexible Server ships 0.8.2 for PG13-18 as of the 2026-07-10 extensions-versions doc

**api surface**
- CREATE EXTENSION vector; (per-database, after allowlisting via azure.extensions)
- Column type: embedding vector(768)
- Index: CREATE INDEX ... USING hnsw (embedding vector_cosine_ops) WITH (m = ..., ef_construction = ...)
- Query operator: ORDER BY embedding <=> :query_vector LIMIT k (cosine distance)
- Functions: cosine_distance(vector, vector), l2_distance(vector, vector), inner_product(vector, vector), vector_dims(vector)
- Session tuning: SET hnsw.ef_search = ...
- az postgres flexible-server parameter set --name azure.extensions --value vector,pg_trgm (provisioning-time allowlist)

**pitfalls**
- Extension must be allowlisted via the `azure.extensions` server parameter before `CREATE EXTENSION vector;` will succeed on Azure Flexible Server -- a GCP-side migration script that skips this step will fail.
- The extension and binary name on Azure is `vector`, not `pgvector`; any script or doc referencing `pgvector` as the CREATE EXTENSION name needs correcting.
- Azure's supported pgvector version (0.8.2) lags upstream's latest (0.8.7); do not depend on upstream-only fixes/features from 0.8.3-0.8.7 until Azure's extensions-versions table reflects them.
- pgvector's unreleased 0.9.0 line is planned to drop PostgreSQL 13 and 14 support and add async I/O for HNSW [uncertain] -- treat as a future compatibility risk, not a current constraint.
- Several 0.7.4/0.8.3/0.8.4 upstream releases fixed HNSW vacuum/build bugs; confirm Azure's bundled 0.8.2 behaves correctly under the project's existing HNSW index workload before relying on vacuum-heavy update patterns.
- Dimension limits (16,000 for standard vectors) are far above the build's 768-dim requirement, so no schema change is needed, but don't assume unlimited dimensionality if embedding models change later.

*As of: Azure docs dated 2026-07-10 (extensions-versions, how-to-use-pgvector, how-to-allow-extensions) and 2026-09-14 (release-notes); upstream pgvector CHANGELOG through 0.8.7 (2026-10-01), with 0.9.0 listed as unreleased*

**Sources**
- [pgvector GitHub repository (README)](https://github.com/pgvector/pgvector) (official-docs) -- "pgvector ... Open-source vector similarity search for Postgres ... Supports: exact and approximate nearest neighbor search, L2 distance, inner product, cosine distance, L1 distance, Hamming distance, and Jaccard distance ... HNSW ... IVFFlat"
- [pgvector CHANGELOG](https://raw.githubusercontent.com/pgvector/pgvector/master/CHANGELOG.md) (official-docs) -- "0.9.0 (unreleased) ... Added asynchronous I/O for HNSW indexes ... Dropped support for Postgres 13 and 14"
- [Vector Search in Azure Database for PostgreSQL Flexible Server](https://learn.microsoft.com/en-us/azure/postgresql/extensions/how-to-use-pgvector) (official-docs) -- "Although the PostgreSQL community refers to this extension as pgvector, the name of the binary and the extension itself is simply `vector`. ... CREATE EXTENSION vector;"
- [Allow Extensions in Azure Database for PostgreSQL Flexible Server](https://learn.microsoft.com/en-us/azure/postgresql/extensions/how-to-allow-extensions) (official-docs) -- "az postgres flexible-server parameter set --resource-group <resource_group> --server-name <server> --name azure.extensions --value "<extension_name>,<extension_name>""
- [List of Extensions and Modules by Name in Azure Database for PostgreSQL Flexible Server](https://learn.microsoft.com/en-us/azure/postgresql/extensions/concepts-extensions-versions) (official-docs) -- "vector ... is a vector data type and ivfflat and hnsw access methods. | PostgreSQL version 18/17/16/15/14/13 | 0.8.2 | 12 | 0.7.0 | 11 | 0.5.1"
- [Release Notes for Azure Database for PostgreSQL flexible server](https://learn.microsoft.com/en-us/azure/postgresql/release-notes/release-notes) (official-docs) -- "Release: May 2025 ... Pgvector 0.8.0 extension ... Release: July 2024 ... General availability of Pgvector 0.7.0 extension ... Release: November 2023 ... General availability of Pgvector 0.5.1 extension"


### Official documentation: pg_trgm
*Find the OFFICIAL documentation for "pg_trgm": its current stable version, how it is installed or enabled, the API surface this build will use, and any breaking changes or pitfalls in the last 2 years (prioritise 2025-2026 current Azure offerings).*

pg_trgm is a core PostgreSQL contrib module (official docs at postgresql.org/docs/current/pgtrgm.html) providing trigram-based text similarity and fuzzy LIKE/ILIKE/regex matching via GiST or GIN indexes; it is installed with a plain `CREATE EXTENSION pg_trgm;` since it is a 'trusted' extension. On Azure Database for PostgreSQL Flexible Server it is fully supported on all current major versions (11-18) but must first be allow-listed via the `azure.extensions` server parameter (restart required) before `CREATE EXTENSION` will succeed — unlike `vector`/pgvector it does not need `shared_preload_libraries`. The API surface this build needs (similarity scoring for fuzzy query matching alongside pgvector HNSW search) is unchanged in the last 2 years; the only notable recent change is a correctness/crash bug (CVE-2026-2007, fixed in PG 18.2 with a follow-up fix in 18.3) affecting strict_word_similarity() under ICU locales with single-byte encodings, which does not affect typical UTF8 setups.

**Key findings**
- Official docs confirm pg_trgm is documented for PostgreSQL 14 through 18 (current) at postgresql.org/docs/current/pgtrgm.html; installed with `CREATE EXTENSION pg_trgm;`, usable by non-superusers with CREATE privilege because it is a 'trusted' module.
- Core API: functions `similarity(text,text)`, `word_similarity`, `strict_word_similarity`, `show_trgm`; operators `%`, `<%`/`%>`, `<<%`/`%>>`, distance operators `<->`, `<<->`/`<->>`, `<<<->`/`<->>>`; GUCs `pg_trgm.similarity_threshold` (default 0.3), `word_similarity_threshold` (0.6), `strict_word_similarity_threshold` (0.5).
- `show_limit()`/`set_limit()` functions are deprecated in favor of the `pg_trgm.similarity_threshold` GUC (long-standing deprecation, not a recent change).
- GiST and GIN operator classes (`gist_trgm_ops`, `gin_trgm_ops`) support `%`/`<%`/`<<%` similarity operators, `LIKE`/`ILIKE` (since PG 9.1), regex `~`/`~*` (since PG 9.3), and equality.
- On Azure Flexible Server, pg_trgm is in the official extensions-by-version list (learn.microsoft.com/.../concepts-extensions-versions) at module version 1.6 for PostgreSQL 14-18, 1.5 for PG 13, 1.4 for PG 11-12; no `shared_preload_libraries` flag required (no asterisk in the table).
- Azure requires allow-listing pg_trgm in the `azure.extensions` server parameter (Portal: Settings > Parameters, or `az postgres flexible-server parameter set --name azure.extensions --value pg_trgm,...`) before `CREATE EXTENSION pg_trgm;` will work; a server restart/deployment is triggered when this parameter changes.
- If pg_trgm is not allow-listed first, Azure returns the specific error: "extension 'pg_trgm' is not allow-listed for users in Azure Database for PostgreSQL" (per Microsoft Q&A thread, consistent with the official how-to-allow-extensions doc).
- Recent correctness fix: CVE-2026-2007, with an oversight/follow-up fix shipped in PostgreSQL 18.3 (released 2026-02-26) — `generate_trgm_only` could fail to return an expanded 'bounds' array pointer, causing incorrect `strict_word_similarity()` output or rare crashes; only triggered when ICU locale + certain single-byte encodings cause lower-casing to lengthen the string.
- PostgreSQL 18.0 changed full text search to use the cluster's default collation provider (rather than always libc) to read configuration/dictionaries, which can indirectly affect pg_trgm behavior in clusters defaulting to a non-libc collation provider [uncertain — found via search summary, not opened directly in primary release notes].
- pgvector (`vector` extension, used alongside pg_trgm for the HNSW Vector(768) column) is listed in the same official Azure table at version 0.8.2 across PostgreSQL 11-18, confirming both extensions coexist on the same supported version matrix.

**Recommendations**
- In Bicep/deployment automation, set the `azure.extensions` server parameter to include `pg_trgm,vector` (plus any others) BEFORE running migration SQL that issues `CREATE EXTENSION pg_trgm;` — the create will fail otherwise, and the parameter change itself triggers a restart, so do it early in provisioning, not interleaved with app deploys.
- No `shared_preload_libraries` change is needed for pg_trgm itself (unlike e.g. pg_cron or pgaudit), simplifying the Bicep parameter set versus other Azure PG extensions.
- Use `CREATE EXTENSION IF NOT EXISTS pg_trgm;` in migrations for idempotency; it is safe to run as the migration-owning role since it's a trusted extension.
- Keep using the standard `%` operator / `similarity()` and GIN (`gin_trgm_ops`) index exactly as today — no API changes are required for the port; this is config/allow-listing work only, not a code port.
- If targeting PostgreSQL 18 specifically, pin to at least 18.3 (or apply the equivalent minor-version patch) to pick up the CVE-2026-2007 follow-up fix, especially if any ICU locale with a single-byte encoding is in use; UTF8-only deployments are effectively unaffected.
- Document the allow-list step explicitly in the RUNBOOK/README since it is an Azure-specific gotcha with no equivalent on self-managed Postgres or the current GCP Cloud SQL setup.

**current version:** pg_trgm module version 1.6 (bundled with PostgreSQL 14-18 on Azure Flexible Server per official Azure extensions-versions table); PostgreSQL itself currently at major version 18 (patch 18.3)

**api surface**
- CREATE EXTENSION pg_trgm;
- similarity(text, text) -> real
- word_similarity(text, text) / strict_word_similarity(text, text) -> real
- % operator (similarity match) and <-> distance operator for ORDER BY ... LIMIT nearest-match queries
- CREATE INDEX ... USING GIN (col gin_trgm_ops); for fast LIKE/ILIKE/regex and % search
- SET pg_trgm.similarity_threshold = <float>; (and word/strict word threshold GUCs)
- Azure-only: az postgres flexible-server parameter set --name azure.extensions --value pg_trgm,... (or Portal > Parameters > azure.extensions)

**pitfalls**
- Azure Flexible Server blocks CREATE EXTENSION pg_trgm unless it is first added to the azure.extensions allow-list parameter; this is Azure-specific and not present on self-hosted Postgres or (per this build's prior stack) Cloud SQL
- Changing azure.extensions triggers a server parameter deployment/restart — must be sequenced before running app migrations in automation
- CVE-2026-2007 / its 18.3 follow-up fix: strict_word_similarity() could return incorrect results or rarely crash under ICU locale + single-byte encoding combinations where lower-casing lengthens the string; irrelevant for standard UTF8 deployments but worth noting if locale config changes
- show_limit()/set_limit() are deprecated long-standing API (predates the 2-year window) — use the pg_trgm.similarity_threshold GUC instead, not a recent break but still a common trap in older sample code
- PG18's switch to using the cluster's default collation provider (rather than always libc) for some text-processing paths can subtly change behavior on non-libc-default clusters [uncertain — summarized from search results, not confirmed by directly reading PG18 release notes in full]

*As of: PostgreSQL docs: current (PostgreSQL 18) as of page fetch 2026-11-02; Azure extensions-by-version and allow-extensions docs carry ms.date 2026-07-10 (updated 2026-07-13); PG 18.3 release notes dated 2026-02-26*

**Sources**
- [PostgreSQL: Documentation: current: F.35. pg_trgm](https://www.postgresql.org/docs/current/pgtrgm.html) (official-docs) -- "pg_trgm module provides functions and operators for determining the similarity of alphanumeric text based on trigram matching, as well as index operator classes that support fast searching for similar strings... CREATE EXTENSION pg_trgm;"
- [Allow Extensions in Azure Database for PostgreSQL Flexible Server - Microsoft Learn](https://learn.microsoft.com/en-us/azure/postgresql/extensions/how-to-allow-extensions) (official-docs) -- "Before creating extensions for an Azure Database for PostgreSQL flexible server, add them to the allow list... az postgres flexible-server parameter set ... --name azure.extensions --value "<extension_name>,<extension_name>""
- [List of Extensions and Modules by Name in Azure Database for PostgreSQL Flexible Server - Microsoft Learn](https://learn.microsoft.com/en-us/azure/postgresql/extensions/concepts-extensions-versions) (official-docs) -- "pg_trgm provides text similarity measurement and index searching based on trigrams. | PostgreSQL version | Extension or module version | | 18 | 1.6 | | 17 | 1.6 | | 16 | 1.6 | | 15 | 1.6 | | 14 | 1.6 | | 13 | 1.5 | | 12 | 1.4 | | 11 | 1.4 |"
- [PostgreSQL: Release Notes 18.3](https://www.postgresql.org/docs/release/18.3/) (official-docs) -- "Fix oversight in the fix for CVE-2026-2007 ... If the "bounds" array needed to be expanded ... generate_trgm_only didn't return the modified array pointer to its caller. That would lead to incorrect output from strict_word_similarity() and related functions, or in rare cases a crash."
- [pg_trgm Extension Not Allowed on Azure Database for PostgreSQL Flexible Server](https://learn.microsoft.com/en-us/answers/questions/5537068/pg-trgm-extension-not-allowed-on-azure-database-fo) (forum) -- "extension 'pg_trgm' is not allow-listed for users in Azure Database for PostgreSQL"


### Official documentation: Azure Container Apps
*Find the OFFICIAL documentation for "Azure Container Apps": its current stable version, how it is installed or enabled, the API surface this build will use, and any breaking changes or pitfalls in the last 2 years (prioritise 2025-2026 current Azure offerings).*

Azure Container Apps (ACA) is Microsoft's serverless container platform (Microsoft.App resource provider) and is the target compute for this build's FastAPI app plus scheduled/async workloads (Container Apps Jobs). It is enabled per-subscription by registering the Microsoft.App (and Microsoft.OperationalInsights) resource providers and installing the `containerapp` Azure CLI extension; apps and jobs are both deployed via Bicep/ARM resources (`Microsoft.App/containerApps`, `Microsoft.App/jobs`) or `az containerapp` / `az containerapp job` CLI commands. The ARM API surface this build needs is: managed environment creation, `containerApps` (HTTP ingress, secrets, registries, revisions) and `jobs` (Manual/Schedule/Event trigger types) resources, now at GA API version 2026-07-01. Key 2025-2026 pitfalls: CLI extensions stopped enabling preview features by default from May 2024 (need `--allow-preview true` for preview features), the ARM schema has repeatedly added/removed preview-only properties (`extendedLocation`, `imageType`, `runningState`) between preview and GA API versions, Service Connector (Preview) on Container Apps retires 2026-03-30, and a new Container Apps Express preview tier appeared at Build 2026 that should NOT be relied on for this GA-targeted build.

**Key findings**
- Official overview (ms.date 2026-07-07) confirms Container Apps is a serverless platform managed via Azure CLI extension, portal, or ARM templates; supports jobs run on-demand/schedule/event, KEDA-based autoscale (incl. scale-to-zero for non-CPU/memory rules), revisions, and Dapr for apps (not jobs).
- Resource provider registration required: `az provider register --namespace Microsoft.App` and `--namespace Microsoft.OperationalInsights` before first use (quickstart doc, ms.date 2025-02-03).
- CLI extension install/upgrade: `az extension add --name containerapp --upgrade`; since May 2024 preview features require `--allow-preview true` added to that command.
- Container Apps Jobs support exactly three trigger types: Manual, Schedule (cron, 5-field, evaluated in UTC), Event (KEDA custom scalers) — per official 'Jobs in Azure Container Apps' page, ms.date 2026-09-16.
- Microsoft.App/jobs ARM/Bicep API versions observed via official change-log (updated 2026-09-21): ...2024-10-02-preview, 2025-01-01 (GA), 2025-02-02-preview, 2025-07-01 (GA), 2025-10-02-preview, 2026-01-01 (GA), 2026-03-02-preview, 2026-07-01 (GA, latest). Preview versions repeatedly add `extendedLocation`/`imageType`/`runningState`; the following GA version removes them — do not pin to a preview-only property.
- Jobs REST 'start' and 'executions' examples in official docs still use api-version=2023-05-01 in sample calls — docs examples lag the latest GA API version; verify the api-version used actually matches intended behavior rather than copying samples verbatim.
- Permissions warning (official docs): built-in roles 'Container Apps Jobs Contributor' and 'Container Apps Jobs Operator' both include `Microsoft.App/jobs/*/action`, which also matches `listSecrets` — holders can read job secrets in plaintext; avoid wildcard actions in custom roles.
- Jobs restrictions (official docs): Dapr and ingress (incl. custom domains/SSL) are NOT supported on Container Apps Jobs — only on Container Apps.
- Execution history for scheduled/event jobs is capped at the 100 most recent successful + failed executions; use the environment's log provider for full history.
- Long-running job replicas can be interrupted by platform maintenance; official guidance is to set replicaRetryLimit >= 1 and design for at-least-once processing.
- Service Connector (Preview) on Azure Container Apps is being retired 2026-03-30 per the official azure-container-apps GitHub issue tracker — do not build the Postgres/ACA wiring on it.
- At Build 2026, Microsoft announced 'Azure Container Apps Express' as a new public-preview environment tier that removes the separate environment-creation step — still preview as of research date, avoid for this production-targeted build.

**Recommendations**
- Pin Bicep templates to a named GA API version for `Microsoft.App/containerApps` and `Microsoft.App/jobs` (latest observed GA: 2026-07-01) rather than 'latest', since preview-only properties flip in/out between releases.
- Use `Microsoft.App/jobs` with trigger type Schedule for recurring batch tasks (e.g. nightly report/sync jobs) and Manual or Event for on-demand/queue-triggered work (e.g. OCR/Graph import jobs), matching the PRD's Container Apps Jobs requirement.
- Register `Microsoft.App` and `Microsoft.OperationalInsights` providers and install the `containerapp` CLI extension (`az extension add --name containerapp --upgrade`, no `--allow-preview` needed unless a specific preview feature is required) as part of the Bicep/deployment runbook.
- Do not use Service Connector (Preview) for the Container Apps <-> Postgres Flexible Server wiring given its 2026-03-30 retirement; use managed identity + connection string/secret via Key Vault references instead, consistent with the 'no plaintext secrets' acceptance criterion.
- Avoid Container Apps Express (preview, Build 2026) for the production deployment target; use the standard environment + containerApps/jobs resources so `az deployment` with Bicep behaves predictably in a fresh subscription (acceptance criterion 9).
- When defining custom RBAC roles for job start/stop, avoid `Microsoft.App/jobs/*/action` wildcards (it grants `listSecrets`); grant only `read`, `start/action`, `stop/action`, `stop/execution/action`, `executions/read`, `execution/read` as needed.
- Do not rely on Dapr or ingress features inside Container Apps Jobs — those are app-only; keep HTTP-facing retrieval/handler logic in the Container App, batch/OCR/import work in Jobs.

**current version:** No semantic product version; latest confirmed GA ARM/Bicep API version for Microsoft.App/jobs (and tracking Microsoft.App/containerApps) is 2026-07-01 as of the official change-log fetched 2026-09-21 [uncertain: whether 2026-07-01 is still the newest GA as of 2026-11-02, and whether containerApps shares this exact version cadence]

**api surface**
- az provider register --namespace Microsoft.App / Microsoft.OperationalInsights
- az extension add --name containerapp --upgrade (CLI extension required for az containerapp/job commands)
- az containerapp env create / az containerapp create (HTTP ingress, secrets, registries, revisions)
- az containerapp job create --trigger-type Manual|Schedule|Event (cron via --cron-expression; event via --scale-rule-* )
- az containerapp job start / az containerapp job execution list
- Bicep resource Microsoft.App/managedEnvironments, Microsoft.App/containerApps, Microsoft.App/jobs@<GA api-version>
- jobs.configuration: manualTriggerConfig | scheduleTriggerConfig | eventTriggerConfig, secrets, registries, replicaTimeout/replicaRetryLimit/parallelism/replicaCompletionCount
- REST: POST .../providers/Microsoft.App/jobs/{job}/start and GET .../jobs/{job}/executions (pin an explicit, current api-version rather than copying the 2023-05-01 used in docs samples)

**pitfalls**
- Preview-only ARM properties (extendedLocation, imageType, runningState) are added in *-preview versions and removed again in the next GA version — building against a preview version risks a schema change at GA.
- Azure CLI/PowerShell extensions no longer auto-enable preview Container Apps features since May 2024; omitting --allow-preview silently hides preview commands rather than erroring clearly.
- Container Apps Jobs do not support Dapr or ingress/custom domains/SSL — do not architect OCR/import jobs assuming inbound HTTP or Dapr service invocation.
- Built-in Jobs Contributor/Operator roles implicitly grant listSecrets via the Microsoft.App/jobs/*/action wildcard; custom roles must enumerate explicit actions to avoid unintended secret exposure.
- Execution history retention is capped at 100 entries for scheduled/event jobs; long-term audit of job runs must go through Log Analytics, not the executions API alone.
- Service Connector (Preview) integration with Container Apps is being retired 2026-03-30 — do not adopt it for new Postgres/secret wiring.
- Container Apps Express (preview, announced Build 2026) changes the environment-creation workflow but is not GA; mixing it with standard Bicep-provisioned environments is unsupported for this build's fresh-subscription provisioning requirement.

*As of: Official pages fetched carry ms.date/updated_at stamps of 2025-02-03 through 2026-09-21; API version change-log fetched reflects data current as of 2026-09-21. Treat 2026-07-01 as the latest confirmed GA ARM API version at research time (2026-11-02).*

**Sources**
- [Azure Container Apps overview](https://learn.microsoft.com/en-us/azure/container-apps/overview) (official-docs) -- "Azure Container Apps is a serverless platform for running containerized applications without managing the underlying infrastructure... Run jobs on-demand, on a schedule, or based on events."
- [Quickstart: Deploy an existing container image with the command line](https://learn.microsoft.com/en-us/azure/container-apps/get-started-existing-container-image) (official-docs) -- "Starting in May 2024, Azure CLI extensions no longer enable preview features by default. To access Container Apps preview features, install the Container Apps extension with --allow-preview true."
- [Jobs in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/jobs) (official-docs) -- "A job's trigger type determines how the job is started. The following trigger types are available: Manual, Schedule, Event... The following features aren't supported: Dapr; Ingress and related features such as custom domains and SSL certificates."
- [Microsoft.App/jobs - Bicep, ARM template & Terraform AzAPI reference](https://learn.microsoft.com/en-us/azure/templates/microsoft.app/jobs) (official-docs) -- "description: Azure Microsoft.App/jobs syntax and properties to use in Azure Resource Manager templates for deploying the resource. API version latest"
- [API change log for Microsoft.App/jobs](https://learn.microsoft.com/en-us/azure/templates/microsoft.app/change-log/jobs) (official-docs) -- "## 2026-07-01
Removed:
- ExtendedLocation
Updated:
- Container: Removed property 'imageType'... ## 2025-01-01
Removed:
- ExtendedLocation"
- [RETIREMENT: Service Connector (Preview) on Azure Container Apps will be retired on March 30, 2026](https://github.com/microsoft/azure-container-apps/issues/1566) (repo) -- "Service Connector (Preview) on Azure Container Apps will be retired on March 30, 2026."


### Official documentation: Azure Container Apps Jobs
*Find the OFFICIAL documentation for "Azure Container Apps Jobs": its current stable version, how it is installed or enabled, the API surface this build will use, and any breaking changes or pitfalls in the last 2 years (prioritise 2025-2026 current Azure offerings).*

[removed by OSA: this line looked like an instruction aimed at an AI (exfiltration)]

**Key findings**
- Official concept doc 'Jobs in Azure Container Apps' (learn.microsoft.com/en-us/azure/container-apps/jobs), ms.date 2026-09-16, confirms three trigger types: Manual, Schedule (cron, UTC), Event (KEDA-based custom scalers).
- Jobs run in the same Container Apps managed environment as apps (share networking/logging) but do not support Dapr or ingress/custom domains/SSL — confirmed in the 'Jobs restrictions' section of the same page.
- Core job settings/CLI params: --trigger-type, --replica-timeout, --replica-retry-limit, --parallelism, --replica-completion-count, --polling-interval (event jobs, default 30s), --cron-expression (schedule jobs), --scale-rule-name/--scale-rule-type/--scale-rule-metadata/--scale-rule-auth (event jobs).
- Execution history for scheduled/event jobs is capped at the 100 most recent successful + failed executions; full history requires querying the environment's logs provider.
- RBAC: built-in 'Container Apps Jobs Contributor' and 'Container Apps Jobs Operator' roles both include the `Microsoft.App/jobs/*/action` wildcard, which also matches `listSecrets/action` — Microsoft explicitly warns to build a custom role instead if plaintext-secret exposure is undesired.
- Security warning (current as of the Sept 2026 doc revision): anyone holding `Microsoft.App/jobs/start/action` can submit a start-execution override template referencing a known secret name or available managed identity and read its value inside the container they control.
- Job execution start/override uses the REST operation `POST .../jobs/{name}/start?api-version=<ver>`; the doc's own example still shows api-version=2023-05-01 but the resource provider's current default/stable API version (per the Jobs REST API reference page, defaultMoniker) is 2026-07-01, with 2025-01-01 and 2025-07-01 also valid recent stable versions; Bicep resource types exist for each (e.g. Microsoft.App/jobs@2025-01-01).
- Long-running job replicas can be interrupted by routine platform maintenance; Microsoft's documented mitigation is replicaRetryLimit >= 1 plus designing the workload for at-least-once processing — directly relevant to Graph-import/backfill jobs that may run long.
- Container settings and the Microsoft.App/jobs ARM schema support containers[], registries[] (ACR via registryServer/username/passwordSecretRef), secrets[], and resources{cpu,memory} — same object model as Container Apps.

**Recommendations**
- Use Manual trigger type (`--trigger-type Manual`) for the Graph import job and any OCR A/B batch job, invoked on demand via `az containerapp job start` or the REST start operation from a controlled identity/CI pipeline — not Schedule, to keep import runs explicit and reviewable.
- Pin Bicep templates to a single explicit, current stable API version for Microsoft.App/jobs (e.g. 2025-01-01 or 2025-07-01) rather than 'latest', and record that version in the Bicep param file for reproducibility across the fresh-subscription provisioning test (acceptance criterion 9).
- Set replicaRetryLimit >= 1 and design the import/backfill job for at-least-once/idempotent processing, since Microsoft documents that platform maintenance can interrupt long-running replicas.
- Do not grant the built-in Jobs Contributor/Operator roles broadly to CI identities that only need to start jobs; define a custom role limited to `Microsoft.App/jobs/read`, `start/action`, `stop/action`, `executions/read` to avoid incidental `listSecrets` exposure, matching the project's no-plaintext-secrets constraint.
- Store ACR credentials and any job secrets (DB connection strings, API keys) as Container Apps job `secrets[]` referenced via secretRef, sourced from Key Vault/managed identity rather than inline values, to satisfy the no-hardcoded-secrets acceptance criterion.
- Do not rely on Dapr or ingress inside the job container — both are unsupported for Container Apps Jobs; any inbound HTTP needs for the retrieval callable must live in the Container App, not the Job.

**current version:** Resource Manager API Microsoft.App/jobs stable default version 2026-07-01 (per REST API reference defaultMoniker); 2025-01-01 and 2025-07-01 also current stable versions usable in Bicep; az containerapp job CLI group is GA (built into current az CLI, no extension required)

**api surface**
- az containerapp job create --trigger-type {Manual|Schedule|Event} --replica-timeout --replica-retry-limit --parallelism --replica-completion-count --image --cpu --memory [--cron-expression | --scale-rule-name/--scale-rule-type/--scale-rule-metadata/--scale-rule-auth]
- az containerapp job start --name --resource-group [--yaml <override-template>]
- az containerapp job execution list --name --resource-group
- az containerapp job show --query properties.template
- Bicep/ARM resource Microsoft.App/jobs@<api-version> with properties.configuration.{manualTriggerConfig|scheduleTriggerConfig|eventTriggerConfig}, replicaRetryLimit, replicaTimeout, triggerType, secrets[], registries[], environmentId, template.containers[]
- REST POST /subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.App/jobs/{name}/start?api-version=<ver>
- REST GET .../jobs/{name}/executions?api-version=<ver>
- RBAC actions: Microsoft.App/jobs/read, start/action, stop/action, executions/read, execution/read, managedEnvironments/read

**pitfalls**
- Built-in Container Apps Jobs Contributor/Operator roles include a wildcard `Microsoft.App/jobs/*/action` that also grants `listSecrets/action` — plaintext secret exposure risk unless a scoped custom role is used instead.
- A caller with only `start/action` can override the execution template to reference known secret names and any managed identity available to the container, effectively reading secrets without `listSecrets` permission — documented as a current warning on the Jobs doc.
- Dapr and ingress (custom domains, SSL) are explicitly unsupported inside Container Apps Jobs.
- Execution history UI/CLI list is capped at the 100 most recent executions for scheduled/event jobs; full audit trail requires the environment's log provider (Log Analytics).
- Long-running job replicas can be interrupted by routine platform maintenance/security updates; replicaRetryLimit of 0 (the create-command default in examples) leaves no retry safety net — must be explicitly raised for import/backfill jobs.
- Multiple active API versions exist in parallel (2023-05-01 through 2026-07-01); documentation examples still show the older 2023-05-01 in REST snippets, so Bicep/CLI deployments must explicitly pin a version rather than copy doc examples verbatim.

*As of: 2026-09-16 (concept doc revision) / 2026-10-23 (REST API reference page revision); RP stable API version 2026-07-01 current as of research date 2026-11-02*

**Sources**
- [Jobs in Azure Container Apps | Microsoft Learn](https://learn.microsoft.com/en-us/azure/container-apps/jobs) (official-docs) -- "Azure Container Apps jobs enable you to run containerized tasks that run for a finite duration and then stop... Job trigger types: Manual, Schedule, Event."
- [Jobs - REST API (Azure Azure Container Apps) | Microsoft Learn](https://learn.microsoft.com/en-us/rest/api/resource-manager/containerapps/jobs?view=rest-resource-manager-containerapps-2025-07-01) (official-docs) -- "Service: Azure Container Apps / API Version: 2025-07-01 ... defaultMoniker: rest-resource-manager-containerapps-2026-07-01 ... Other Supported Versions: 2023-04-01-preview ... 2026-01-01 ... 2026-07-01"
- [az containerapp job | Microsoft Learn](https://learn.microsoft.com/en-us/cli/azure/containerapp/job?view=azure-cli-latest) (official-docs) -- "az containerapp job — command group for managing Container Apps jobs (create, start, stop, delete, execution list)."
- [Microsoft.App/jobs 2025-01-01 - Bicep, ARM template & Terraform AzAPI reference](https://learn.microsoft.com/en-us/azure/templates/microsoft.app/2025-01-01/jobs) (official-docs) -- "resource symbolicname 'Microsoft.App/jobs@2025-01-01' = { ... }"


### Official documentation: Azure Container Registry
*Find the OFFICIAL documentation for "Azure Container Registry": its current stable version, how it is installed or enabled, the API surface this build will use, and any breaking changes or pitfalls in the last 2 years (prioritise 2025-2026 current Azure offerings).*

Azure Container Registry (ACR) is Azure's managed private Docker/OCI registry, created via `az acr create` or a Bicep/ARM `Microsoft.ContainerRegistry/registries` resource (current stable API version 2025-04-01, with 2025-06-01-preview as latest preview). For this build, ACR will be provisioned via Bicep as a Basic or Standard SKU registry, images pushed via `az acr build`/docker, and Container Apps/Container Apps Jobs will pull from it using managed identity (AcrPull role) rather than the admin account. No ACR-specific breaking changes block this build, but Helm 2 legacy repos were retired (March 2025), Docker Content Trust is being deprecated (new DCT disabled after May 2026, fully removed 2028, replaced by Notary Project signing), and old API versions (2017-03-01-GA and earlier previews) are deprecated with 2017-03-01-GA ending support September 2026 — the Bicep templates must target 2025-04-01 or later, not an old pinned version.

**Key findings**
- ACR intro page (ms.date 2026-02-11, updated 2026-06-12) confirms three SKUs — Basic, Standard, Premium — all sharing the same data-plane APIs; only Premium adds geo-replication, private endpoints, content trust, customer-managed keys.
- SKU limits page (updated 2026-10-16): Basic = 10 GiB included storage / 40 TiB max; Standard = 100 GiB / 40 TiB; Premium = 500 GiB / 100 TiB. Basic/Standard share the same API rate limits (e.g. DataplaneWrite 2,000 r/m per registry); Premium gets higher limits.
- Current stable Bicep/ARM resource API version for Microsoft.ContainerRegistry/registries is 2025-04-01 (GA); 2025-06-01-preview and 2025-05-01-preview exist as previews (confirmed via learn.microsoft.com template reference pages, page ms.date 2024-12-09, last content update 2026-10-20).
- API version deprecation: 2016-06-27-preview, 2017-06-01-preview, 2018-02-01-preview ended support October 2023; 2017-03-01-GA deprecated (announced Sept 2023), support ends September 2026 — per official ACR FAQ page (ms.date 2026-02-04).
- Helm 2 / legacy 'Helm repositories' retirement: `az acr helm push` retired Jan 21 2025; `az acr helm` command group and all non-OCI Helm charts retired/deleted March 30 2025 (official ACR docs via search, Microsoft Learn breaking-changes content).
- Docker Content Trust (DCT) deprecation: deprecation started March 31 2025; after May 31 2026 DCT cannot be enabled on new or previously-unenabled registries; full removal March 31 2028. Notary Project is the recommended replacement — per official 'container-registry-content-trust-deprecation' doc and FAQ page.
- Official FAQ explicitly recommends: 'Move to a newer version of the ACR API... If you consume an API via SDKs, move to a newer version of the SDK' to avoid deprecated-API errors.
- Admin account is documented as intended for single-user/testing use only; official guidance recommends individual Entra ID identities for users and service principals/managed identity for headless (CI/CD, Container Apps) scenarios — relevant since this build should use managed identity for Container Apps → ACR pulls, not the admin account.

**Recommendations**
- Use Bicep resource type `Microsoft.ContainerRegistry/registries` with apiVersion `2025-04-01` (current GA) rather than an older or preview version, to avoid the deprecated-API path flagged by Azure.
- Choose Basic SKU for this small school-bot workload (storage and throughput limits are more than sufficient); Standard/Premium add no feature this build needs (no geo-replication or private endpoints required).
- Disable the registry admin account (`adminUserEnabled: false`) and grant the Container Apps managed identity the `AcrPull` role instead, per official guidance against sharing admin credentials.
- Do not rely on Helm chart push to ACR (legacy Helm repo support was removed March 2025) — not relevant to this build but avoid any lingering Helm-based deployment tooling.
- No action needed on Docker Content Trust unless the build was planning to enable DCT; if image signing is desired later, plan for Notary Project rather than DCT given its 2028 removal timeline.
- If any Bicep/ARM template pins an API version, verify it is not 2017-03-01-GA or an earlier preview — those are deprecated or approaching end-of-support (Sept 2026 for 2017-03-01-GA).

**current version:** Stable ARM/Bicep API version 2025-04-01 for Microsoft.ContainerRegistry/registries (preview: 2025-06-01-preview); service tiers Basic/Standard/Premium current as of 2026-10

**api surface**
- Bicep/ARM resource: Microsoft.ContainerRegistry/registries@2025-04-01 (properties: sku.name = Basic|Standard|Premium, adminUserEnabled: bool)
- az acr create -g <rg> -n <registry> --sku Basic
- az acr login -n <registry> / docker login <registry>.azurecr.io
- docker build/push/pull against <registry>.azurecr.io (Docker Registry HTTP API V2 at https://<registry>.azurecr.io/v2/)
- az acr build (Tasks-based remote image build, used for CI image builds)
- AcrPull / AcrPush RBAC role assignment to Container Apps managed identity for registry access
- az acr show-usage / az acr check-health for diagnostics

**pitfalls**
- Legacy 'Helm repositories' and `az acr helm` command group fully retired March 30 2025; non-OCI Helm charts were deleted — not relevant unless Helm charts were planned, but confirms any pre-2025 Helm-based ACR tutorials are stale.
- Docker Content Trust (DCT) deprecated starting March 31 2025; cannot be newly enabled after May 31 2026; full removal March 31 2028 — do not build new tooling around DCT, use Notary Project if signing is needed.
- API versions 2016-06-27-preview, 2017-06-01-preview, 2018-02-01-preview are already past support (ended Oct 2023); 2017-03-01-GA support ends September 2026 — ensure Bicep templates/SDKs are pinned to 2025-04-01 or later.
- Classic (pre-SKU) registries are no longer supported at all — any very old ARM template referencing 'classic' registry type will fail; must use Basic/Standard/Premium SKU.
- Admin account shows all users as a single identity for rate-limiting and auditing purposes — official docs discourage its use for multi-consumer scenarios (e.g., both CI/CD and Container Apps pulling); use managed identity/RBAC instead.
- Firewall/network rule changes can take a few minutes to propagate; don't assume instant effect when scripting network-restricted ACR access for Container Apps.

*As of: 2026-02 to 2026-10 (ACR intro doc dated 2026-02-11/updated 2026-06-12; FAQ dated 2026-02-04; SKU limits doc updated 2026-10-16; Bicep template reference pages updated 2026-10-20, documenting stable API 2025-04-01 and preview 2025-06-01-preview)*

**Sources**
- [Introduction to Azure Container Registry](https://learn.microsoft.com/en-us/azure/container-registry/container-registry-intro) (official-docs) -- "Container registries are available in three tiers (SKUs): Basic, Standard, and Premium... Premium registries support additional capabilities and have greater storage and limits."
- [Azure Container Registry FAQ](https://learn.microsoft.com/en-us/azure/container-registry/container-registry-faq) (official-docs) -- "The following API versions have been deprecated... 2017-03-01-GA | September 2023 | September 2026... Move to a newer version of the ACR API."
- [Azure Container Registry SKU Features and Limits](https://learn.microsoft.com/en-us/azure/container-registry/container-registry-skus) (official-docs) -- "Included storage (GiB): Basic 10, Standard 100, Premium 500... Geo-replication: N/A, N/A, Supported (Premium only)."
- [Microsoft.ContainerRegistry/registries 2025-04-01 - Bicep, ARM template & Terraform AzAPI reference](https://learn.microsoft.com/en-us/azure/templates/microsoft.containerregistry/2025-04-01/registries) (official-docs) -- "description: Azure Microsoft.ContainerRegistry/registries syntax and properties to use in Azure Resource Manager templates for deploying the resource. API version 2025-04-01"
- [Microsoft.ContainerRegistry/registries 2025-06-01-preview - Bicep, ARM template & Terraform AzAPI reference](https://learn.microsoft.com/en-us/azure/templates/microsoft.containerregistry/2025-06-01-preview/registries) (official-docs) -- "Microsoft.ContainerRegistry/registries 2025-06-01-preview - Bicep, ARM template & Terraform AzAPI reference"


### Official documentation: Azure Key Vault
*Find the OFFICIAL documentation for "Azure Key Vault": its current stable version, how it is installed or enabled, the API surface this build will use, and any breaking changes or pitfalls in the last 2 years (prioritise 2025-2026 current Azure offerings).*

Azure Key Vault is Microsoft's managed secrets/keys/certificates store; this build will use only the data-plane Secrets API (store API keys, DB creds, WhatsApp tokens) via the azure-keyvault-secrets Python SDK plus azure-identity for managed-identity auth from Container Apps. No installation of a 'server' is needed — you provision a Microsoft.KeyVault/vaults resource (e.g. via Bicep) and call the REST/SDK data-plane API against https://{vault}.vault.azure.net. Current stable data-plane API is 2025-07-01 and control-plane (ARM) API is 2026-02-01; the Python secrets SDK is at 4.12.0 (Oct 28, 2026) and now requires Python >=3.10. The key trend over the research window is a steady, well-documented push from access-policy to Azure RBAC authorization, culminating in RBAC becoming the default for new vaults as of API version 2026-02-01 (March 2026) — access policies remain supported for existing vaults, so this is additive, not a breaking removal.

**Key findings**
- Latest Python data-plane SDK: azure-keyvault-secrets 4.12.0, published 2026-10-28, requires Python >=3.10 (3.9 support dropped); regenerated against Key Vault API version 2026-04-01 [uncertain-marked only for the exact release date, verified via PyPI fetch].
- Core usage pattern (official devguide): `from azure.identity import DefaultAzureCredential; from azure.keyvault.secrets import SecretClient; SecretClient(vault_url=..., credential=DefaultAzureCredential())` then `set_secret`/`get_secret`.
- Authentication best practice (official): use Managed Identity for Azure-hosted apps (recommended); service-principal+secret or +certificate are explicitly 'not recommended' due to rotation burden — directly applicable to Container Apps managed identity.
- Key Vault has a two-plane model: control plane (ARM, resource create/delete/RBAC vs access-policy assignment) and data plane (actual get/set of secrets), each with separate SDKs and separate API-version tracks.
- May 2023 (official 'what's new'): Azure RBAC became the *recommended* data-plane authorization model over access policies.
- March 2026 (official 'what's new'): new control-plane API versions 2026-02-01 (stable) and 2026-03-01-preview released; Azure RBAC is now the *default* access-control model for newly-created vaults under API 2026-02-01 (existing vaults unaffected unless explicitly migrated; access policies still fully supported).
- March 2026: control-plane management SDKs on API versions older than 2026-02-01 will stop working when those versions retire on 2027-02-27 — only affects control-plane (azure-mgmt-keyvault/Bicep deploy tooling), not the data-plane secrets SDK used at runtime.
- March 2026: preview control-plane API versions are being deprecated with a 90-day notice (except 2026-04-01-preview) — build should pin Bicep/ARM templates to a stable API version, not a preview one.
- June 2023: Key Vault enforces TLS 1.2 or higher for all client connections.
- azure-keyvault-secrets 4.11.2 fixed a security bug where an authentication challenge was cached before the challenge resource was verified; 4.12.0 further hardened challenge-cache reuse — pin to >=4.11.2, ideally latest.
- Official guidance: store only true secrets (connection strings, passwords, API keys, SSH keys) in Key Vault; non-secret config should go in Azure App Configuration, not Key Vault tags.

**Recommendations**
- Use RBAC authorization (enableRbacAuthorization: true) on the Bicep-provisioned vault and assign the Container Apps managed identity the built-in 'Key Vault Secrets User' (read) or 'Key Vault Secrets Officer' (read/write) role — this matches current Microsoft default/recommended posture (default since API 2026-02-01, recommended since May 2023) and satisfies 'no plaintext secrets' acceptance criteria.
- Authenticate from Container Apps with a user-assigned managed identity + DefaultAzureCredential (or ManagedIdentityCredential) — never service-principal secrets, matching the secrets/config adapter's job of swapping GCP Secret Manager for Key Vault without code using credentials directly.
- Pin azure-keyvault-secrets to >=4.11.2 (ideally 4.12.0) and azure-identity to a current release; require Python >=3.10 in the runtime image since 4.12.0 dropped 3.9.
- In Bicep templates, target a stable ARM API version (2026-02-01 or 2025-05-01) for Microsoft.KeyVault/vaults, not a preview version, given the active preview-deprecation cycle.
- Cache fetched secrets in-process at startup (per official performance guidance) rather than calling get_secret on every request, to avoid Key Vault throttling limits.
- Do not store non-secret config (project IDs, feature flags) in Key Vault; keep that in pydantic-settings/env/App Configuration, reserving Key Vault strictly for credentials — this also helps the 'no hardcoded GCP project ids' grep criterion stay clean.

**current version:** Data-plane SDK: azure-keyvault-secrets 4.12.0 (Python, Oct 2026); data-plane REST API 2025-07-01 (stable); control-plane/ARM API 2026-02-01 (stable, recommended)

**api surface**
- azure.identity.DefaultAzureCredential / ManagedIdentityCredential (token acquisition for Container Apps managed identity)
- azure.keyvault.secrets.SecretClient(vault_url, credential)
- SecretClient.get_secret(name) / .set_secret(name, value) / .list_properties_of_secrets() / .begin_delete_secret(name)
- Bicep/ARM resource Microsoft.KeyVault/vaults with properties.enableRbacAuthorization=true
- Built-in RBAC roles: 'Key Vault Secrets User' (read) and 'Key Vault Secrets Officer' (read/write), assigned via Microsoft.Authorization/roleAssignments scoped to the vault
- Vault data-plane endpoint https://{vault-name}.vault.azure.net/ (TLS 1.2+ enforced)

**pitfalls**
- azure-keyvault-secrets 4.12.0 dropped Python 3.9 support — pin runtime to Python >=3.10 or stay on an older SDK pin.
- RBAC is now the default for brand-new vaults under API 2026-02-01 (March 2026) but older/existing vaults keep access policies unless explicitly migrated — don't assume RBAC is already on for any pre-existing vault; set enableRbacAuthorization explicitly in Bicep.
- Control-plane management SDKs (azure-mgmt-keyvault, ARM/Bicep tooling) pinned to API versions older than 2026-02-01 stop working when those versions retire 2027-02-27 — irrelevant to the runtime secrets client but relevant to deploy tooling/CI.
- Preview control-plane API versions are being deprecated on a rolling 90-day notice (March 2026 wave) — avoid pinning Bicep templates to a preview apiVersion.
- A security bug (auth challenge cached before resource verification) existed in SDK versions before 4.11.2 — ensure the dependency pin is >=4.11.2.
- TLS 1.2+ has been mandatory since June 2023; any legacy HTTP client config forcing TLS 1.0/1.1 will fail to connect.
- Per-vault/per-region transaction throttling limits apply (service-limits doc referenced in developer's guide) — cache secrets at app startup rather than per-request fetches to avoid 429s.

*As of: Docs: 'basic-concepts' updated 2026-04-10, 'developers-guide' updated 2026-05-13, 'whats-new' updated 2026-09-08 (content through March 2026 entries); SDK: azure-keyvault-secrets 4.12.0 published 2026-10-28 per PyPI.*

**Sources**
- [What is Azure Key Vault? (Microsoft Learn)](https://learn.microsoft.com/en-us/azure/key-vault/general/basic-concepts) (official-docs) -- "Using a managed identity makes solving this problem simpler by giving Azure services an automatically managed identity in Microsoft Entra ID... We recommend this approach as a best practice."
- [Azure Key Vault developer's guide (Microsoft Learn)](https://learn.microsoft.com/en-us/azure/key-vault/general/developers-guide) (official-docs) -- "The data plane controls access to keys, certificates, and secrets. You can use Azure RBAC with Key Vault for access control through the data plane... Use Azure Key Vault to store only secrets for your application."
- [What's new for Azure Key Vault (Microsoft Learn)](https://learn.microsoft.com/en-us/azure/key-vault/general/whats-new) (official-docs) -- "Azure Key Vault API version 2026-02-01 introduces Azure RBAC as the default access control model for newly created key vaults... Both Azure RBAC and access policies remain fully supported."
- [azure-keyvault-secrets · PyPI](https://pypi.org/project/azure-keyvault-secrets/) (repo) -- "The current release is 4.12.0... requires Python >=3.10... Regenerated with Key Vault API version 2026-04-01."


### Official documentation: Azure Managed Identity
*Find the OFFICIAL documentation for "Azure Managed Identity": its current stable version, how it is installed or enabled, the API surface this build will use, and any breaking changes or pitfalls in the last 2 years (prioritise 2025-2026 current Azure offerings).*

Azure Managed Identity is a platform capability (not a versioned product) that lets Azure resources obtain Microsoft Entra ID tokens without stored credentials, via system-assigned or user-assigned identities. For this build, Container Apps and Container Apps Jobs get a user-assigned managed identity (configured in Bicep), and the Python code uses the azure-identity SDK's DefaultAzureCredential/ManagedIdentityCredential to authenticate to Azure OpenAI/Foundry, Key Vault, ACR image pull, and Postgres Flexible Server (Entra auth, token used as the PG password). The current azure-identity Python package is 1.27.0; the managed-identity mechanics themselves (IDENTITY_ENDPOINT/IDENTITY_HEADER, RBAC role assignment on the target resource) have been stable, with the main recent behavioral change being DefaultAzureCredential's v1.14.0+ continuation policy. Postgres Flexible Server Entra tokens expire in 5-60 minutes and must be refreshed per connection, which matters for the SQLAlchemy adapter.

**Key findings**
- Two managed identity types: system-assigned (tied to one resource's lifecycle) and user-assigned (standalone resource, reusable across Container Apps, Jobs, etc.) — user-assigned is Microsoft's recommended type for multi-resource workloads (Entra ID overview, updated 2026-06-15).
- Container Apps: enable identity via `az containerapp identity assign --system-assigned` / `--user-assigned <ID>`, or Bicep `identity: { type: 'UserAssigned', userAssignedIdentities: {...} }`; an app can have both types simultaneously (type `SystemAssigned,UserAssigned`) (Container Apps managed-identity doc, updated 2026-02-13).
- Container Apps exposes a local REST token endpoint via env vars IDENTITY_ENDPOINT and IDENTITY_HEADER; GET with `resource`, `api-version=2019-08-01` (or later) and optional `client_id`/`principal_id`/`mi_res_id` for a specific user-assigned identity — omit all ID params to default to system-assigned.
- azure-identity for Python current version is 1.27.0 (source link `azure-identity_1.27.0` on the docs page dated 2026-10-26); requires Python 3.10+ and non-EOL Python 3.
- DefaultAzureCredential continuation policy changed in v1.14.0: it now tries every developer credential until one succeeds regardless of prior errors, whereas deployed-service credentials (incl. managed identity) still stop the chain with an exception on failure.
- Container Apps pitfall: when using Azure Identity client library, you must explicitly specify the user-assigned managed identity's client ID if the app has more than one identity attached — there is no implicit default.
- Container Apps token cache for a resource URI persists ~24h; after changing a target resource's role assignment, a cached token with the old permissions may still be returned, and forced refresh isn't supported.
- Init containers cannot use managed identity in consumption-only or dedicated workload-profile environments; API version 2024-02-02-preview added per-identity lifecycle control (`Init`/`Main`/`All`/`None`) to scope which containers/phases can use a given identity.
- Azure Database for PostgreSQL Flexible Server supports Microsoft Entra auth: an Entra access token (resource `https://ossrdbms-aad.database.windows.net`, or `az account get-access-token --resource-type oss-rdbms`) is passed as the PostgreSQL password; tokens are valid only 5-60 minutes and must be fetched fresh per connection, not cached in scripts (Postgres Flexible Server Entra auth doc, updated 2026-09-06).
- Postgres: the Entra admin role has elevated privileges (e.g. CREATEDB) and should not be used for normal app connections; a separate app role/principal should be created via `pgaadauth_create_principal(...)`, and managed identities/service principals are supported as members of synced Entra groups.

**Recommendations**
- Provision a user-assigned managed identity in the Bicep templates (not system-assigned) and attach it to Container Apps and Container Apps Jobs, so the acceptance criterion `az deployment` on a fresh subscription can grant RBAC roles before/alongside resource creation.
- In the Python code, standardize on azure-identity's DefaultAzureCredential for all adapters (OpenAI/Foundry, Key Vault secrets, Postgres token) so the same code path works locally (falls back to Azure CLI credential) and in Container Apps (managed identity) without branching logic.
- Pin azure-identity to >=1.14.0 (ideally current 1.27.0) to get the safer DefaultAzureCredential continuation policy on developer-credential failures.
- If more than one user-assigned identity is ever attached to a Container App, pass the explicit `client_id` into ManagedIdentityCredential/DefaultAzureCredential to avoid ambiguous token requests.
- For the Postgres adapter, implement a SQLAlchemy connection-creator that fetches a fresh Entra token (`oss-rdbms` resource) per new connection rather than caching it, and create a dedicated non-admin Entra-mapped Postgres role for the app identity via `pgaadauth_create_principal`.
- Assign RBAC roles (Key Vault, Postgres Entra role membership, Azure OpenAI/Foundry resource) to the identity's principal ID inside the Bicep templates themselves, not as a manual post-deploy step, to keep the fresh-subscription deployment self-contained.
- After any role-assignment change during testing, allow for the ~24h managed-identity token cache before concluding a permission grant 'didn't work' — re-test with a fresh identity or expect delayed effect.
- Avoid system-assigned-only identities for anything that must be pre-authorized before the compute resource exists (e.g. pre-granting DB/Key Vault access as part of IaC) — use user-assigned for that reason, per Microsoft's own recommendation.

**current version:** Managed Identity is an unversioned Entra ID platform feature; the azure-identity Python SDK that implements ManagedIdentityCredential/DefaultAzureCredential is at 1.27.0 as of the docs page dated 2026-10-27

**api surface**
- azure.identity.DefaultAzureCredential() / ManagedIdentityCredential(client_id=...) — .get_token()/.get_token_info() (Python, used by OpenAI/Foundry, Key Vault, storage adapters)
- az containerapp identity assign/show/remove --system-assigned|--user-assigned <ID> (CLI, also used for Container Apps Jobs)
- Bicep `identity: { type: 'UserAssigned'|'SystemAssigned', userAssignedIdentities: { <resourceId>: {} } }` on containerApps/containerAppJobs resources
- Container Apps REST token endpoint: GET $IDENTITY_ENDPOINT?resource=<uri>&api-version=2019-08-01&client_id=<id>, header X-IDENTITY-HEADER=$IDENTITY_HEADER
- az account get-access-token --resource-type oss-rdbms (or --resource https://ossrdbms-aad.database.windows.net) — token used as PGPASSWORD for Postgres Flexible Server Entra auth
- pgaadauth_create_principal('<role name>', false, false) — creates the non-admin Entra-mapped Postgres role for the app's managed identity

**pitfalls**
- DefaultAzureCredential continuation-policy change in v1.14.0 — developer credentials no longer abort the chain on failure, but deployed credentials (incl. managed identity) still do.
- Must explicitly pass client_id when a Container App has more than one user-assigned identity, or token requests are ambiguous.
- Role-assignment changes may not take effect for up to 24h due to the managed-identity token cache; forced refresh isn't supported.
- Init containers can't use managed identity in consumption-only or dedicated workload-profile environments unless using the 2024-02-02-preview lifecycle (`Init`/`Main`/`All`/`None`) API.
- Postgres Entra tokens expire in 5-60 minutes — must be fetched fresh per connection, not cached/stored in scripts or long-lived connection pools without refresh logic.
- Don't use the Postgres Entra admin identity for app connections — it has elevated permissions (e.g. CREATEDB); create a separate role via pgaadauth_create_principal for the app identity.
- Container Apps created before 2022-04-11 require a new revision when a managed identity is first added (legacy note still in current docs).

*As of: Entra ID managed identities overview updated 2026-06-15; Container Apps managed-identity doc updated 2026-02-13 (ms.date 2025-06-03); azure-identity Python docs updated 2026-10-27 (package 1.27.0); Postgres Flexible Server Entra auth doc updated 2026-09-06*

**Sources**
- [Managed identities for Azure resources - overview](https://learn.microsoft.com/en-us/entra/identity/managed-identities-azure-resources/overview) (official-docs) -- "User-assigned managed identities, which are provisioned independently from compute and can be assigned to multiple compute resources, are the recommended managed identity type for Microsoft services."
- [Managed identities in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/managed-identity) (official-docs) -- "The back-end services for managed identities maintain a cache per resource URI for around 24 hours... Forcing a token refresh isn't supported."
- [Azure Identity client library for Python](https://learn.microsoft.com/en-us/python/api/overview/azure/identity-readme) (official-docs) -- "As of version 1.14.0, DefaultAzureCredential attempts to authenticate with all developer credentials until one succeeds, regardless of any errors previous developer credentials experienced."
- [Use Microsoft Entra ID Authentication in Azure Database for PostgreSQL Flexible Server](https://learn.microsoft.com/en-us/azure/postgresql/security/security-entra-configure) (official-docs) -- "The access token is valid for 5 to 60 minutes. Get the access token before initiating the sign-in to Azure Database for PostgreSQL."


### Official documentation: Microsoft Entra ID
*Find the OFFICIAL documentation for "Microsoft Entra ID": its current stable version, how it is installed or enabled, the API surface this build will use, and any breaking changes or pitfalls in the last 2 years (prioritise 2025-2026 current Azure offerings).*

Microsoft Entra ID (formerly Azure AD) is a continuously-updated cloud identity service, not a versioned library, so 'current version' means the current API/SDK generation rather than a release number. For this build, the relevant surface is: Microsoft Entra Workload ID / Managed Identity on Azure Container Apps and Container Apps Jobs (system- or user-assigned) used to authenticate to Azure Key Vault, Azure Database for PostgreSQL Flexible Server, and Azure Container Registry, accessed in Python via the azure-identity SDK's DefaultAzureCredential/ManagedIdentityCredential. Service-to-service auth (e.g. Graph import, Foundry/OpenAI if key-less) uses the OAuth2 client-credentials flow via login.microsoftonline.com, with client secret, certificate, or federated credential (workload identity federation) as the three supported methods. Documentation is current as of pages dated 2026-01 through 2026-06, i.e. within the research window.

**Key findings**
- Microsoft Entra ID is the renamed, continuously-updated successor to Azure AD; it has no discrete 'version number', confirmed on the official 'What is Microsoft Entra' page (ms.date 2026-06-18).
- Azure Container Apps managed-identity doc (ms.date 2025-06-03, updated 2026-02-13) confirms system-assigned (one per app, tied to app lifecycle) and user-assigned (standalone, multi-app) identities, configurable via portal, az CLI, ARM, YAML, or Bicep ('identity: { type: SystemAssigned }').
- Container Apps exposes an internal token REST endpoint via env vars IDENTITY_ENDPOINT and IDENTITY_HEADER; GET with api-version=2019-08-01 or later and optional client_id for user-assigned identity returns a Bearer token usable against any Entra-protected resource.
- Init containers in consumption-only and dedicated workload-profile environments cannot access managed identities; API version 2024-02-02-preview adds per-identity lifecycle scoping (Init/Main/All/None) to limit which containers can use which identity.
- Managed-identity token cache is held ~24h per resource URI server-side; updating an RBAC role assignment does not force-refresh a cached token, and forced refresh is not supported (relevant to debugging 'permission granted but still denied' issues).
- azure-identity Python SDK latest stable release is 1.27.0 (released 2026-10-26 per PyPI), exposing DefaultAzureCredential, ManagedIdentityCredential, ClientSecretCredential, CertificateCredential, ClientAssertionCredential, WorkloadIdentityCredential, plus async equivalents under azure.identity.aio.
- OAuth2 client-credentials flow doc (ms.date 2026-01-30, updated 2026-06-15) specifies POST https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token with grant_type=client_credentials and scope=<resource>/.default; three credential forms are client_secret, certificate-based client_assertion, or federated-credential client_assertion (workload identity federation).
- Refresh tokens are never issued in the client-credentials flow; a fresh token request must be made against /token when the prior access_token (default expires_in 3599s) expires.
- Azure Database for PostgreSQL Flexible Server supports Microsoft Entra authentication (PostgreSQL-only, Entra-only, or both) and a dedicated managed-identity connection path, documented on learn.microsoft.com/azure/postgresql/security/security-entra-concepts and security-connect-with-managed-identity.
- Per a 2026 Postgres-at-Microsoft roundup (secondary source, not official docs): Entra token-refresh helper libraries for Python became available and an April 2026 maintenance release fixed PgBouncer auth failures when Entra tokens exceeded 4KB with PgBouncer — treat as [uncertain] pending confirmation on an official release-notes page.

**Recommendations**
- Use user-assigned Managed Identity (not a client-secret app registration) for the Container Apps/Jobs that call Key Vault, Postgres Flexible Server, and ACR — avoids storing any Entra secret in the repo or app config, satisfying the 'no plaintext secrets' acceptance criterion.
- In Bicep, set identity.type = 'UserAssigned' on both the Container App and Container Apps Job, and grant it RBAC roles (Key Vault Secrets User, ACRPull) plus an Entra-based Postgres role rather than embedding DB passwords.
- In the Python secrets/config adapter, use azure-identity's DefaultAzureCredential so the same code authenticates locally (Azure CLI credential) and in Container Apps (managed identity) without branching logic.
- If any service call requires client-credentials (e.g. a Graph import job running outside Container Apps), prefer a federated credential (workload identity federation) over a client secret to keep zero long-lived secrets, per the OAuth2 doc's explicit recommendation.
- Account for the ~24h managed-identity token cache when testing new RBAC role assignments during setup — expect stale-permission errors to persist up to a day, not a code bug.
- Do not rely on init containers having managed-identity access if running on consumption/dedicated workload profiles; do any Entra-authenticated setup work in the main container or move it to a Container Apps Job.
- Verify current Azure PostgreSQL Entra maintenance notes directly on the official release-notes page before relying on the PgBouncer/4KB-token fix claim, since that came from a secondary summary, not the primary changelog.

**current version:** No version number — Microsoft Entra ID is a continuously-updated cloud service; relevant SDK is azure-identity (Python) 1.27.0 (released 2026-10-26) and Microsoft identity platform v2.0 token endpoint

**api surface**
- Container Apps/Jobs Bicep: identity: { type: 'UserAssigned', userAssignedIdentities: { <resourceId>: {} } }
- Internal token endpoint: GET $IDENTITY_ENDPOINT?resource=<entra-resource-uri>&api-version=2019-08-01 with header X-IDENTITY-HEADER: $IDENTITY_HEADER
- Python: azure.identity.DefaultAzureCredential() / ManagedIdentityCredential(client_id=...) passed to Azure SDK clients (Key Vault, Postgres token acquisition)
- OAuth2 client credentials: POST https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token with grant_type=client_credentials, scope=<resource>/.default
- az CLI: az containerapp identity assign --name <app> --resource-group <rg> --system-assigned | --user-assigned <id>
- Azure Database for PostgreSQL Flexible Server Entra-authenticated connection (security-connect-with-managed-identity) in place of password auth for the pgvector database

**pitfalls**
- Managed-identity tokens are cached ~24h per resource URI server-side; new RBAC role assignments may appear not to take effect immediately and forced refresh is unsupported.
- Init containers cannot use managed identity in consumption-only or dedicated workload-profile environments; only API version 2024-02-02-preview's identitySettings lifecycle control changes this.
- Containers apps deployed before 2022-04-11 require a new revision to pick up a newly added managed identity — not relevant for a fresh build but worth knowing if reusing an old revision.
- Client-credentials flow never issues a refresh token; the app must re-POST to /token on each expiry (default ~3599s) rather than expecting a refresh_token field.
- Never request scopes spanning multiple resources in one client-credentials call — the /.default scope must target exactly one resource or the token endpoint returns invalid_scope.
- [uncertain] A secondary (non-official) 2026 summary claims an April 2026 Postgres maintenance fix for Entra tokens >4KB breaking PgBouncer auth; confirm on the official Postgres release-notes page before depending on it.
- Microsoft Entra External ID M2M scenarios require a separate Premium add-on license — not applicable to this internal server-to-server build but a cost pitfall if confused with regular Entra ID tenant auth.

*As of: 2026-06-18 (Entra overview), 2026-02-13 (Container Apps managed identity doc update), 2026-06-15 (OAuth2 client credentials flow doc update), 2026-10-26 (azure-identity 1.27.0 PyPI release)*

**Sources**
- [What is Microsoft Entra? - Microsoft Entra | Microsoft Learn](https://learn.microsoft.com/en-us/entra/fundamentals/whatis) (official-docs) -- "Microsoft Entra ID is the foundational product of Microsoft Entra. It's a cloud-based identity and access management service..."
- [Managed identities in Azure Container Apps | Microsoft Learn](https://learn.microsoft.com/en-us/azure/container-apps/managed-identity) (official-docs) -- "A managed identity from Microsoft Entra ID allows your container app to access other Microsoft Entra protected resources."
- [OAuth 2.0 client credentials flow on the Microsoft identity platform | Microsoft Learn](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-client-creds-grant-flow) (official-docs) -- "To get a token by using the client credentials grant, send a POST request to the /token Microsoft identity platform... client_id, scope, client_secret, grant_type=client_credentials."
- [azure-identity · PyPI](https://pypi.org/project/azure-identity/) (official-docs) -- "Latest Stable Version: 1.27.0 (released October 26, 2026)... Azure Identity library provides Microsoft Entra ID token-based authentication support across the Azure SDK."
- [Microsoft Entra Authentication in Azure Database for PostgreSQL Flexible Server | Microsoft Learn](https://learn.microsoft.com/en-us/azure/postgresql/security/security-entra-concepts) (official-docs) -- "Azure Database for PostgreSQL supports three modes of authentication: PostgreSQL authentication only, Microsoft Entra authentication only, and both."
- [What's new with Postgres at Microsoft, 2026 edition](https://techcommunity.microsoft.com/blog/adforpostgresql/whats-new-with-postgres-at-microsoft-2026-edition/4526963) (article) -- "Entra ID token refresh libraries are now available for .NET, Python, and Java... In April 2026, an issue was fixed that could lead to authentication failures when Microsoft Entra ID token size exceeds 4 KB while using PgBouncer."


### Official documentation: Bicep
*Find the OFFICIAL documentation for "Bicep": its current stable version, how it is installed or enabled, the API surface this build will use, and any breaking changes or pitfalls in the last 2 years (prioritise 2025-2026 current Azure offerings).*

Bicep is Microsoft's open-source, free DSL that compiles to ARM JSON templates; current CLI is in the v0.48.x line (v0.48.1, Oct 2026) per the official GitHub releases page, auto-installed by Azure CLI (>=2.20.0) via `az bicep install`/`az bicep upgrade`, or manually via winget/choco/brew/direct download per Microsoft Learn. For this build, the relevant API surface is `az bicep` CLI subcommands plus `az deployment group create/validate/what-if` consuming .bicep/.bicepparam files targeting Microsoft.App (Container Apps + Jobs), Microsoft.ContainerRegistry/registries, and Microsoft.DBforPostgreSQL/flexibleServers resource types. Recent (2025-2026) changes include GA of `@retryOn` and `@nullIfNotFound()` decorators, GA of extendable .bicepparam files, a new local `bicep snapshot` diff command, and a breaking restriction requiring OCI module registries to be on a trusted list.

**Key findings**
- Official install doc (ms.date 2026-07-23) confirms Azure CLI >=2.20.0 auto-installs a self-contained Bicep CLI via `az bicep install`/`az bicep upgrade`/`az bicep version`; manual install via winget 'Microsoft.Bicep', choco, brew, or GitHub release binaries adds `bicep` to PATH separately.
- Bicep CLI releases page (github.com/Azure/bicep/releases) lists v0.48.1 (Oct 5, 2026), v0.47.16 (Sep 8, 2026), v0.46.1 (Jul 30, 2026) as the most recent entries at time of research [uncertain: exact patch/date mapping from tool summary, not manually re-verified line-by-line].
- Bicep CLI commands doc (ms.date 2026-05-14) enumerates the full command set: build, build-params, console (v0.42.1+), decompile, decompile-params, format, generate-params, install (az-only), jsonrpc, lint, list-versions (az-only), publish, restore, snapshot (v0.41.2+), upgrade (az-only), version.
- az deployment group docs (ms.date 2026-08-20) confirm `az deployment group create/validate/what-if` all accept `--template-file` pointing directly at a .bicep file (Bicep CLI invoked automatically) and `--parameters` accepting a .bicepparam file directly.
- Microsoft.App/containerApps latest GA API version is 2026-07-01 per the official Azure resource reference page opened directly; version history runs back through 2025-07-01, 2025-10-02-preview, 2026-01-01, 2026-03-02-preview to 2026-07-01.
- Microsoft.DBforPostgreSQL/flexibleServers latest GA API version appears to be 2025-08-01 with 2026-04-01-preview as newest preview [uncertain: derived from search result snippets, not a fully re-opened page table].
- Microsoft.ContainerRegistry/registries latest GA API version appears to be 2025-04-01 with 2026-09-01-preview as newest preview [uncertain: derived from search result snippets, not a fully re-opened page table].
- Official overview page (ms.date 2026-01-08) states Bicep immediately supports all preview and GA API versions as soon as a resource provider publishes them -- no separate tooling lag.
- Overview page explicitly notes Microsoft Customer Support does not cover Bicep experimental features; use at own risk.
- GitHub releases summary indicates a breaking change in v0.43.1 blocking custom domains for Azure Container Registry, and a more recent change enforcing a trusted-registry list for OCI module restore.

**Recommendations**
- Pin a specific Bicep CLI version in CI (via `az bicep install --version vX.Y.Z` or a pinned Azure CLI image) rather than relying on 'latest', since Azure CLI auto-upgrades Bicep silently and the project targets reproducible `az deployment` runs for acceptance criterion 9.
- Use `az deployment group create --template-file main.bicep --parameters main.bicepparam` (typed .bicepparam, not legacy JSON params) to match current Microsoft Learn guidance and get compile-time parameter validation.
- Explicitly declare resource API versions in Bicep (e.g. Microsoft.App/containerApps@2026-07-01, Microsoft.App/jobs@<matching version>, Microsoft.DBforPostgreSQL/flexibleServers@2025-08-01, Microsoft.ContainerRegistry/registries@2025-04-01) rather than trusting defaults, and re-verify these exact strings against the live resource reference pages before locking the Bicep templates, since two of them were only confirmed via search snippets here.
- Run `az deployment group what-if` (or local `bicep snapshot` for fast offline diffing) before any apply against the fresh subscription required by acceptance criterion 9, to catch unintended resource replacement (e.g. Postgres Flexible Server or ACR SKU changes that force recreation).
- If publishing shared Bicep modules to ACR, confirm the registry is on an allowed/trusted list given the OCI module-restore trust restriction introduced in recent Bicep versions; avoid relying on implicit trust of arbitrary registries.
- Do not depend on Bicep experimental features (e.g. OCI publishing to non-ACR registries) for production IaC in this build, since Microsoft Support explicitly excludes experimental features from assistance.

**current version:** Bicep CLI v0.48.1 (Oct 2026 release line) [uncertain]

**api surface**
- az bicep install / az bicep upgrade / az bicep version / az bicep list-versions
- bicep build | build-params | lint | format | decompile | decompile-params | generate-params | restore | publish | snapshot | console
- az deployment group create --template-file <main.bicep> --parameters <main.bicepparam>
- az deployment group validate / what-if --template-file ... --parameters ...
- Microsoft.App/containerApps@2026-07-01 (Container Apps)
- Microsoft.App/jobs@<matching current API version> (Container Apps Jobs) [uncertain]
- Microsoft.ContainerRegistry/registries@2025-04-01 (ACR) [uncertain]
- Microsoft.DBforPostgreSQL/flexibleServers@2025-08-01 (Postgres Flexible Server) [uncertain]

**pitfalls**
- Azure CLI's bundled Bicep CLI instance is separate from any manually installed one and is NOT added to PATH -- Azure PowerShell deployments fail unless Bicep CLI is installed manually and separately (per install doc).
- `bicep install`/`bicep upgrade` do not work in air-gapped environments; the executable must be manually placed in $HOME/.azure/bin (or Windows equivalent) -- relevant if the school's Azure tenant has restricted network egress.
- OCI module restore now enforces a trusted-registry list; publishing/consuming Bicep modules from arbitrary registries can silently fail post-upgrade.
- v0.43.1 blocked usage of custom domains for Azure Container Registry -- avoid relying on ACR custom domain names in templates.
- Resource API versions move fast (monthly-ish); hardcoding an old API version in checked-in Bicep can silently miss new required properties or hit deprecated-field warnings at `az deployment` time -- re-pin versions near ship date, not from this research alone.
- Bicep snapshot is local/offline and will fail or return placeholders for environment functions (subscription().id, resourceGroup().name) unless context flags are passed -- it is not a substitute for `az deployment group what-if` as a final pre-deploy check.

*As of: Install and CLI-commands docs dated 2026-07-23 and 2026-05-14 respectively; overview doc dated 2026-01-08; az deployment group doc dated 2026-08-20; GitHub releases observed October 2026*

**Sources**
- [Install Bicep tools - Azure Resource Manager | Microsoft Learn](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/install) (official-docs) -- "You must have Azure CLI version 2.20.0 or later installed... To verify your current version, run: az --version... To upgrade to the latest version, use: az bicep upgrade"
- [What is Bicep? - Azure Resource Manager | Microsoft Learn](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/overview) (official-docs) -- "Bicep immediately supports all preview and GA versions for Azure services... Microsoft Customer Support doesn't provide assistance for issues resulting from the use of Bicep experimental features"
- [Bicep CLI commands - Azure Resource Manager | Microsoft Learn](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/bicep-cli) (official-docs) -- "By using Bicep CLI v0.41.2 or newer, you can use the snapshot command to create a normalized, deterministic representation of a Bicep deployment"
- [az deployment group | Microsoft Learn](https://learn.microsoft.com/en-us/cli/azure/deployment/group) (official-docs) -- "Create a deployment at resource group scope from a bicepparam parameter file: az deployment group create --resource-group testrg --parameters parameters.bicepparam"
- [Releases · Azure/bicep · GitHub](https://github.com/Azure/bicep/releases) (repo) -- "v0.48.1 (October 5, 2026)... retryOn() decorator GA... extendable parameter files are now GA"
- [Microsoft.App/containerApps - Bicep, ARM template & Terraform AzAPI reference](https://learn.microsoft.com/en-us/azure/templates/microsoft.app/containerapps) (official-docs) -- "resource symbolicname 'Microsoft.App/containerApps@2026-07-01' = { ... }"
- [Microsoft.DBforPostgreSQL/flexibleServers - Bicep, ARM template & Terraform AzAPI reference](https://learn.microsoft.com/en-us/azure/templates/microsoft.dbforpostgresql/flexibleservers) (official-docs) -- "API version latest ... ms.date 2024-12-09 ... updated_at 2026-10-20"
- [Microsoft.ContainerRegistry/registries - Bicep, ARM template & Terraform AzAPI reference](https://learn.microsoft.com/en-us/azure/templates/microsoft.containerregistry/registries) (official-docs) -- "Microsoft.ContainerRegistry/registries 2025-04-01 - Bicep, ARM template & Terraform AzAPI reference"


### Official documentation: Microsoft Graph API
*Find the OFFICIAL documentation for "Microsoft Graph API": its current stable version, how it is installed or enabled, the API surface this build will use, and any breaking changes or pitfalls in the last 2 years (prioritise 2025-2026 current Azure offerings).*

Microsoft Graph has one stable REST surface, v1.0, at https://graph.microsoft.com, documented at learn.microsoft.com/en-us/graph/overview (updated 2026-04-16). For this build's 'Graph import' (pulling past-paper files from OneDrive/SharePoint), the relevant surface is the Files API (Drive/DriveItem resources) under app-only (daemon) auth via Microsoft Entra ID, called with the official Python SDK 'msgraph-sdk' (current 1.65.0, released 2026-10-22, requires Python 3.10+) plus 'azure-identity' for ClientSecretCredential. No install/enable step beyond registering an Entra app and consenting application permissions (e.g. Files.Read.All or Sites.Read.All) and pip-installing the SDK. The main forward-looking pitfall is the April 1, 2027 retirement of pre-authenticated 'tempauth' download URLs, which affects file download/preview/thumbnail/upload-session APIs this build will use.

**Key findings**
- Microsoft Graph's single stable endpoint is https://graph.microsoft.com/v1.0; a parallel /beta endpoint exists for preview features and is not meant for production (learn.microsoft.com/en-us/graph/overview, ms.date 2026-04-15).
- Python SDK package name is 'msgraph-sdk' (pip install msgraph-sdk); current version is 1.65.0 released 2026-10-22, requires Python >=3.10, offers an async-first API, and depends on kiota abstractions for error handling (APIError) [from PyPI page opened directly].
- azure-identity must be installed separately for auth credential classes (e.g. ClientSecretCredential, DeviceCodeCredential) per learn.microsoft.com/en-us/graph/sdks/sdk-installation (ms.date 2024-11-07, updated 2025-08-06 — slightly older than the 2-year window but still the current official page).
- Files/Drive API: Drive and DriveItem are the two core resources; common paths are /me/drive, /drives/{drive-id}, /sites/{site-id}/drive, /sites/{site-id}/drives, and /drives/{drive-id}/root/children, per learn.microsoft.com/en-us/graph/api/resources/onedrive (ms.date 2024-03-12, updated 2024-11-21 — older source, file resource model has been stable since).
- Auth model: app-only (daemon/service) access uses Microsoft Entra ID application permissions (app roles), distinct from delegated/user-based scopes; recommended for background automation with no signed-in user (learn.microsoft.com/en-us/graph/auth/auth-concepts, updated 2025-08-06).
- Breaking change: pre-authenticated 'tempauth' URLs for SharePoint/OneDrive retire April 1, 2027; affects download file content, upload session creation, long-running copy/monitor actions, previews, thumbnails, and format conversion — apps must instead present a separate Entra ID token for the SharePoint audience or opt into a future tenant setting to keep using Graph tokens (Microsoft 365 Developer Blog, devblogs.microsoft.com, read directly).
- Unrelated-to-files but notable 2025-2026 Graph changes found via search (not independently opened, so marked uncertain): enforcement of restricted updates to sensitive mail properties begins 2026-12-31, and markAsJunk API deprecated 2025-12-30 — these don't affect this build's file-import scope.

**Recommendations**
- Use the v1.0 Graph endpoint only (never beta) for the import job to keep behavior stable in production.
- Install 'msgraph-sdk' plus 'azure-identity' in the Python requirements for the Graph-import adapter/job, pinned to a specific version given the SDK's frequent biweekly release cadence.
- Authenticate the import job as app-only (client credentials / ClientSecretCredential) since it runs unattended as a Container Apps Job, not on behalf of a signed-in user.
- Request the minimum application permissions needed (e.g. Sites.Read.All or Files.Read.All, scoped to specific SharePoint sites via an application access policy if possible) rather than broad tenant-wide Sites.FullControl.All.
- Store the Entra app's client secret or certificate in the project's secrets adapter/Key Vault, never in plaintext config, satisfying the no-plaintext-secrets acceptance criterion.
- When downloading past-paper files, call the driveItem content endpoint directly with the Graph access token rather than relying on an embedded @microsoft.graph.downloadUrl redirect, since those pre-authenticated URLs are being retired April 1, 2027 — build the importer against token-based auth from day one to avoid a future migration.
- Treat the Files/Drive API pages (onedrive.md, dated 2024) as the authoritative but slightly dated reference; cross-check the current Graph changelog at the time of implementation for any newer Files API changes.

**current version:** REST API: v1.0 (stable production endpoint; /beta exists for preview). Python SDK: msgraph-sdk 1.65.0, released 2026-10-22

**api surface**
- GET/POST https://graph.microsoft.com/v1.0 endpoint (stable, production)
- GET /sites/{site-id}/drive and /sites/{site-id}/drives — locate SharePoint document library for past-paper files
- GET /drives/{drive-id}/root/children or /root:/path/to/folder:/children — list/enumerate DriveItems
- GET /drives/{drive-id}/items/{item-id}/content — download file content directly with bearer token (avoids tempauth dependency)
- msgraph-sdk Python client (GraphServiceClient) + azure.identity.ClientSecretCredential for app-only auth
- Microsoft Entra ID app registration with application permissions: Files.Read.All or Sites.Read.All

**pitfalls**
- Pre-authenticated (tempauth) URL retirement on April 1, 2027 for download/upload-session/preview/thumbnail/copy-monitor/conversion APIs — must migrate to Entra ID bearer tokens for file access, not raw redirect URLs.
- msgraph-sdk is large (~36MB) and releases roughly twice monthly; pin a version to avoid unexpected breaking changes between Container Apps builds.
- App-only (application permission) access to Files.Read.All/Sites.Read.All requires tenant admin consent and, ideally, scoping via application access policies — cannot be granted by the importing service itself.
- Using /me/* endpoints requires a signed-in user (delegated access) and will not work for an unattended app-only import job; must use /sites/{id}/drive or /drives/{id} instead.
- [uncertain] Broader 2025-2026 Graph changes (sensitive mail property restriction enforcement 2026-12-31, markAsJunk deprecation 2025-12-30) were found only via search summaries, not opened directly, and are unrelated to this build's file-import scope.

*As of: 2026-11-02 (Graph overview page updated 2026-04-16; msgraph-sdk Python 1.65.0 released 2026-10-22; onedrive/auth-concepts pages last substantively updated 2024-2025)*

**Sources**
- [Microsoft Graph overview - Microsoft Graph | Microsoft Learn](https://learn.microsoft.com/en-us/graph/overview) (official-docs) -- "The Microsoft Graph API offers a single endpoint, https://graph.microsoft.com, to provide access to rich, people-centric data and insights in the Microsoft cloud"
- [Install a Microsoft Graph SDK - Microsoft Graph | Microsoft Learn](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) (official-docs) -- "The Microsoft Graph Python SDK is available on PyPI. pip install msgraph-sdk"
- [msgraph-sdk · PyPI](https://pypi.org/project/msgraph-sdk/) (official-docs) -- "This SDK allows you to build applications using the v1.0 of Microsoft Graph; supports both sync and async credential classes from azure.identity"
- [Working with files in Microsoft Graph - Microsoft Graph v1.0 | Microsoft Learn](https://learn.microsoft.com/en-us/graph/api/resources/onedrive?view=graph-rest-1.0) (official-docs) -- "Microsoft Graph exposes two resource types for working with files: Drive ... and DriveItem ... /sites/{site-id}/drive - Access the default Drive (document library) for the given SharePoint site"
- [Authentication and authorization basics - Microsoft Graph | Microsoft Learn](https://learn.microsoft.com/en-us/graph/auth/auth-concepts) (official-docs) -- "App-only access is used in scenarios such as automation and backup, and is mostly used by apps that run as background services or daemons."
- [Pre-authenticated (tempauth) URLs are retiring: move to Microsoft Entra ID tokens before April 1, 2027 - Microsoft 365 Developer Blog](https://devblogs.microsoft.com/microsoft365dev/pre-authenticated-tempauth-urls-are-retiring-move-to-microsoft-entra-id-tokens-before-april-1-2027/) (article) -- "Starting April 1, 2027, affected Microsoft Graph file APIs will no longer return pre-authenticated URLs ... Download a file, driveItem: createUploadSession, and driveItem: preview"


### Official documentation: SharePoint
*Find the OFFICIAL documentation for "SharePoint": its current stable version, how it is installed or enabled, the API surface this build will use, and any breaking changes or pitfalls in the last 2 years (prioritise 2025-2026 current Azure offerings).*

Microsoft Graph (v1.0, stable) is the official API for reading SharePoint content; this build will use it under 'Graph import' to pull past-paper documents from a SharePoint site/document library via an Entra ID app-only (client credentials) registration. SharePoint itself requires no install — it is a hosted SaaS service enabled per-tenant; access is enabled by registering an Entra ID app, granting it Microsoft Graph permissions (Sites.Selected recommended over broad Sites.Read.All), and for Sites.Selected explicitly granting that app access to the specific site collection via POST /sites/{siteId}/permissions. The legacy SharePoint Add-in model and Azure ACS app-only auth were fully retired April 2, 2026, so any import code must use modern Entra ID app-only auth, not ACS tokens. No breaking changes affect the core Graph /sites, /drive, /drive/items endpoints this build needs; the main 2025-2026 pitfalls are the ACS/Add-in retirement and a deprecated GrantedToIdentities permission property (replaced by GrantedToIdentitiesV2).

**Key findings**
- Microsoft Graph SharePoint API is documented at api version 'v1.0' (stable) and 'beta'; sharepoint.md page content dated 2024-03-14, last updated 2024-11-21 [uncertain: may have had minor unlogged edits since]
- Core read scenario: GET /sites/{site-id}, /sites/{site-id}/drive, /sites/{site-id}/drives, /sites/{site-id}/lists/{list-id}/items; sites can be addressed by hostname:/path as well as by ID
- SharePoint Add-ins (SharePoint-hosted and provider-hosted) reached end of life in SharePoint Online on April 2, 2026; Azure ACS auth for SharePoint stopped working the same date
- CSOM, JSOM and SharePoint REST APIs are NOT retired by the Add-in/ACS retirement; Graph is the recommended first choice, REST/CSOM only for gaps Graph doesn't cover
- Sites.Selected is the recommended app-only permission for scoping an app to one site collection; it grants NO access until an admin/owner calls POST /sites/{siteId}/permissions with a role (read/write/owner/fullcontrol) for that app
- Granting that permission itself requires Sites.FullControl.All or Sites.Selected+FullControl/Owner on the target site — a one-time admin setup step outside the app's own runtime permissions
- Response schema shows GrantedToIdentities is deprecated in favor of GrantedToIdentitiesV2 on permission objects
- Microsoft Graph Search API (/search/query) does NOT enforce Sites.Selected scoping in app-only scenarios — avoid it for a site-restricted app; use direct /sites or /drive endpoints instead
- Remote event receivers using Azure ACS stopped working April 2, 2026; replacement is SharePoint Online webhooks or Graph change notifications (subscription on a SharePoint list) if the import ever needs push notifications
- Python Graph SDK (msgraph-sdk-python code sample) states 'Current version is 1.x' as of the fetched permissions-selected-overview page (updated 2026-02-26)

**Recommendations**
- Use Microsoft Graph v1.0 (not beta, not legacy SharePoint REST/CSOM) for the one-off/periodic past-paper import job
- Authenticate via an Entra ID app registration using client-credentials (app-only) flow, not any Azure ACS or SharePoint Add-in auth, since the latter is retired
- Request the Sites.Selected application permission scoped to only the one site/library holding past papers, and have an admin run POST /sites/{siteId}/permissions once to grant that app 'read' role — avoid broad Sites.Read.All/Sites.FullControl.All
- Fetch file content via GET /sites/{site-id}/drive/items/{item-id}/content (driveItem) rather than the Graph Search API, since Search does not respect Sites.Selected scoping in app-only mode
- Do not build on SharePoint Add-ins, Azure ACS auth, or remote event receivers for this import — all are retired or on a deprecation path as of April 2, 2026
- If future real-time sync is needed, use Graph change notifications/webhooks on the list, not ACS-based remote event receivers

**current version:** Microsoft Graph REST API v1.0 (stable); SharePoint Online is a continuously-updated SaaS service with no discrete version number

**api surface**
- GET /sites/{site-id} or /sites/{hostname}:/{relative-path} — resolve the target SharePoint site
- GET /sites/{site-id}/drive and /sites/{site-id}/drives — enumerate document libraries
- GET /sites/{site-id}/drive/items/{item-id}/content — download a file's bytes for OCR/import
- GET /sites/{site-id}/lists/{list-id}/items — enumerate list/library items and metadata
- POST /sites/{siteId}/permissions — admin-side grant of Sites.Selected app-only role on the site collection
- Entra ID OAuth2 client-credentials (app-only) token acquisition with the Sites.Selected application permission

**pitfalls**
- SharePoint Add-in model and Azure ACS app-only auth fully retired April 2, 2026 — do not build or rely on either
- Sites.Selected grants zero access by default; forgetting the admin POST /sites/{siteId}/permissions step silently blocks the app
- Granting that Sites.Selected permission requires Sites.FullControl.All or an equivalent higher-privilege scope — plan for an admin-run one-time setup step, not something the import job can self-serve
- Graph Search API (/search/query) ignores Sites.Selected scoping in app-only mode — do not use it to 'search' for files if relying on Sites.Selected for isolation
- GrantedToIdentities field on permission objects is deprecated in favor of GrantedToIdentitiesV2 — use the V2 field when reading/writing permission grants
- Assigning permissions at list/item/file level breaks inheritance and counts against SharePoint Online's unique-permissions-per-list service limit; prefer site-collection-level Sites.Selected grants for a simple bulk import

*As of: 2026-10-28 (ACS/Add-in retirement FAQ page last updated); SharePoint Graph resource page dated 2024-03-14/updated 2024-11-21; Selected-permissions overview updated 2026-02-26*

**Sources**
- [Working with SharePoint sites in Microsoft Graph - Microsoft Graph v1.0 | Microsoft Learn](https://learn.microsoft.com/en-us/graph/api/resources/sharepoint?view=graph-rest-1.0) (official-docs) -- "The SharePoint API in Microsoft Graph supports... Access to SharePoint sites, lists, and drives (document libraries)... /sites/{site-id}/drive | Access the default drive (document library) for the given site."
- [SharePoint Add-Ins and Azure ACS retirement FAQ | Microsoft Learn](https://learn.microsoft.com/en-us/sharepoint/dev/sp-add-ins/add-ins-and-azure-acs-retirements-faq) (official-docs) -- "SharePoint Add-ins reached end of life in SharePoint Online on April 2, 2026... Using Azure ACS... will stop working from April 2nd 2026... This retirement does not retire SharePoint REST APIs, CSOM, JSOM, or SPFx."
- [Overview of Selected Permissions in OneDrive and SharePoint - Microsoft Graph | Microsoft Learn](https://learn.microsoft.com/en-us/graph/permissions-selected-overview) (official-docs) -- "Sites.Selected | Manages application access at the site collection level... The application must be granted permissions to a list via a call to POST /sites/{siteid}/lists/{listid}/permissions with a specific role."


### Official documentation: OneDrive
*Find the OFFICIAL documentation for "OneDrive": its current stable version, how it is installed or enabled, the API surface this build will use, and any breaking changes or pitfalls in the last 2 years (prioritise 2025-2026 current Azure offerings).*

OneDrive is accessed programmatically via the Microsoft Graph REST API (v1.0), not a separate 'OneDrive API' product; Microsoft's guidance explicitly says the legacy OneDrive API is superseded and the Graph endpoints (drive, driveItem) are the supported path. For this build's 'Graph import' feature, the bot would use app-only (client credentials) auth against Entra ID, then call drive/driveItem endpoints under https://graph.microsoft.com/v1.0 to list and download past-paper files from a OneDrive or SharePoint document library. No installation is needed beyond registering an Entra ID app and (for Python) installing the msgraph-sdk package; there is no 'enabling' OneDrive itself since it's a standard Microsoft 365 service.

**Key findings**
- OneDrive/SharePoint file access is fully folded into Microsoft Graph; the legacy standalone OneDrive API is not the recommended path per the OneDrive dev center docs (learn.microsoft.com/onedrive/developer).
- Core resources: Drive (/me/drive, /drives/{drive-id}, /sites/{site-id}/drive) and DriveItem (/drives/{drive-id}/items/{item-id}), addressable by id or by path using root:/path/to/file syntax.
- List folder contents: GET /drives/{drive-id}/items/{item-id}/children; paginated via @odata.nextLink once results exceed the 200-item default page size.
- Download file content: GET /drives/{drive-id}/items/{item-id}/content returns HTTP 302 redirecting to a time-limited preauthenticated download URL (also exposed as @microsoft.graph.downloadUrl); supports Range header for partial downloads.
- Least-privileged permissions for read/import workflows: Files.Read.All (application permission) or Files.Read (delegated); higher-privilege Files.ReadWrite.All/Sites.Read.All only if write access is needed.
- Python SDK is 'msgraph-sdk' on PyPI, current version 1.65.0 (released 2026-10-22), requires Python 3.10+, installed via pip install msgraph-sdk; client is msgraph.GraphServiceClient with async calls like graph_client.drives.by_drive_id(...).items.by_drive_item_id(...).content.get().
- 2025-2026 breaking changes: Permission resource properties grantedTo/grantedToIdentities are being removed in favor of grantedToV2/grantedToIdentitiesV2 after a 4-year deprecation notice (announced 2025-03-21); no exact final removal date disclosed in the post.
- Pre-authenticated 'tempauth' download/upload URLs (the same mechanism underlying @microsoft.graph.downloadUrl and the /content redirect) are being retired; Graph file APIs stop returning tempauth tokens after 2027-04-01, requiring an Entra ID (or SharePoint) token instead.
- sharedWithMe API is deprecated and will stop returning data after November 2027 — not relevant to this build's planned use (direct drive/folder import, not shared-with-me).

**Recommendations**
- Use the Microsoft Graph v1.0 endpoint (graph.microsoft.com/v1.0) with app-only Entra ID client-credentials auth and the Files.Read.All application permission for a non-interactive import job (matches Container Apps Job model already planned).
- Implement the OneDrive/Graph import adapter against /drives/{drive-id}/items/{item-id}/children for listing and /content (following the 302 or using @microsoft.graph.downloadUrl) for fetching past-paper files, handling @odata.nextLink pagination.
- Install msgraph-sdk (current 1.65.0, Python 3.10+) rather than hand-rolling raw HTTP calls, to stay aligned with Microsoft's supported SDK surface.
- Do not rely on cached/hardcoded download URLs beyond their short validity window, and do not build logic around tempauth query-parameter URLs — fetch fresh @microsoft.graph.downloadUrl per run so the 2027-04-01 tempauth retirement won't break the import job.
- If any permission-related metadata (grantedTo/grantedToIdentities) is ever read from imported items, use grantedToV2/grantedToIdentitiesV2 now rather than the deprecated fields.

**current version:** Microsoft Graph API v1.0 (OneDrive via drive/driveItem resources, no separate OneDrive API version); msgraph-sdk (Python) 1.65.0

**api surface**
- GET /drives/{drive-id} and GET /me/drive (Drive resource)
- GET /drives/{drive-id}/items/{item-id}/children (list folder contents, with @odata.nextLink pagination)
- GET /drives/{drive-id}/items/{item-id}/content (download file content, 302 to @microsoft.graph.downloadUrl)
- Addressing by path: /drives/{drive-id}/root:/path/to/folder:/children
- Entra ID app-only (client credentials) auth with Graph scope Files.Read.All
- Python: msgraph.GraphServiceClient, graph_client.drives.by_drive_id(...).items.by_drive_item_id(...).children.get() / .content.get()

**pitfalls**
- Legacy standalone OneDrive API is not the current recommended surface; must use Microsoft Graph endpoints instead.
- Preauthenticated download URLs (/content redirect, @microsoft.graph.downloadUrl) expire within minutes — fetch and use immediately, don't cache long-term.
- Tempauth-based preauthenticated URLs across file download/upload/preview/thumbnail/convert APIs are being retired by 2027-04-01; plan to use Entra ID tokens against SharePoint/Graph instead.
- Permission resource fields grantedTo/grantedToIdentities are deprecated in favor of grantedToV2/grantedToIdentitiesV2 (announced 2025-03-21); avoid the old fields in any new code.
- Default page size for children listings is 200 items — import logic must handle @odata.nextLink or it will silently miss files in large folders.
- sharedWithMe API is deprecated and stops returning data after November 2027 — don't build the import path on shared-with-me semantics.

*As of: Microsoft Graph v1.0 OneDrive/driveItem docs (list-children updated 2025-11-25, get-content updated 2025-08-27); msgraph-sdk Python 1.65.0 released 2026-10-22; devblogs posts dated 2025-03-21 (permission props) and n.d. tempauth retirement (deadline 2027-04-01)*

**Sources**
- [OneDrive for Developers - OneDrive dev center](https://learn.microsoft.com/en-us/onedrive/developer/?view=odsp-graph-online) (official-docs) -- "The best way to connect to OneDrive, OneDrive for Business, and SharePoint document libraries is the Microsoft Graph."
- [Working with files in Microsoft Graph (OneDrive resource) - v1.0](https://learn.microsoft.com/en-us/graph/api/resources/onedrive?view=graph-rest-1.0) (official-docs) -- "Microsoft Graph exposes two resource types for working with files: Drive ... DriveItem ..."
- [List the contents of a folder - Microsoft Graph v1.0](https://learn.microsoft.com/en-us/graph/api/driveitem-list-children?view=graph-rest-1.0) (official-docs) -- "If a collection exceeds the default page size (200 items), the @odata.nextLink property is returned in the response"
- [Download driveItem content - Microsoft Graph v1.0](https://learn.microsoft.com/en-us/graph/api/driveitem-get-content?view=graph-rest-1.0) (official-docs) -- "Returns a 302 Found response redirecting to a preauthenticated download URL for the file, which is the same URL available through the @microsoft.graph.downloadUrl property"
- [msgraph-sdk · PyPI](https://pypi.org/project/msgraph-sdk/) (official-docs) -- "Latest Version: 1.65.0 ... Install Command: pip install msgraph-sdk ... Supported Python Versions: Python 3.10 and later"
- [Removal of Deprecated SharePoint & OneDrive Permission Resource Properties](https://devblogs.microsoft.com/microsoft365dev/removal-of-deprecated-sharepoint-onedrive-permission-resource-properties/) (official-docs) -- "Update your applications to reference the grantedToV2 and grantedToIdentitiesV2 permissions when using any of the following API calls for SharePoint and OneDrive."
- [Pre-authenticated (tempauth) URLs are retiring: move to Microsoft Entra ID tokens before April 1, 2027](https://devblogs.microsoft.com/microsoft365dev/pre-authenticated-tempauth-urls-are-retiring-move-to-microsoft-entra-id-tokens-before-april-1-2027/) (official-docs) -- "After this date, affected Microsoft Graph file APIs will stop returning URLs with embedded tempauth tokens."


### Official documentation: azure-storage-blob
*Find the OFFICIAL documentation for "azure-storage-blob": its current stable version, how it is installed or enabled, the API surface this build will use, and any breaking changes or pitfalls in the last 2 years (prioritise 2025-2026 current Azure offerings).*

azure-storage-blob is Microsoft's official Python SDK for Azure Blob Storage, used here as the storage adapter to replace google-cloud-storage. Current stable release is 12.31.1 (2026-10-29), installed via `pip install azure-storage-blob`, requiring Python 3.10+. The build will use BlobServiceClient/ContainerClient/BlobClient with DefaultAzureCredential (Managed Identity on Container Apps) for upload_blob/download_blob/list_blobs, plus the azure.storage.blob.aio async variants if the handler is async. The main 2025-2026 pitfall is the Python 3.9 support drop in 12.31.0 (2026-09-30); no other breaking API-shape changes were found for the basic upload/download/list surface in this window.

**Key findings**
- Current stable PyPI version: azure-storage-blob 12.31.1, released 2026-10-29 (confirmed on PyPI and Microsoft Learn page metadata).
- Install: pip install azure-storage-blob; package requires Python 3.10 or later for 12.31.x (dropped Python 3.9 support in 12.31.0, 2026-09-30).
- 12.27.0b1 (2025-06-12) had dropped Python 3.8 support, requiring 3.9+ at that time.
- Four main clients: BlobServiceClient (account-level), ContainerClient (container-level), BlobClient (blob-level), BlobLeaseClient (lease ops).
- Auth options: DefaultAzureCredential/AAD token credential (azure-identity), SAS token string, account shared key, connection string, or anonymous for public containers.
- Async support exists under azure.storage.blob.aio, requiring an async HTTP transport such as aiohttp to be installed separately.
- 12.24.1 (2025-01-22) changed stream iteration guidance: iterate via StorageStreamDownloader.chunks rather than the raw downloader object.
- Client-side encryption v2.0 tamper-detection and SAS timezone-aware datetime handling bugs were fixed as late as 12.30.1/12.31.1 (2026).
- 12.19.0b1 deprecated passing BlobProperties objects directly as blob-name parameters in several APIs (still relevant if upgrading from older pinned versions).

**Recommendations**
- Pin azure-storage-blob>=12.28,<13 (or latest 12.31.x) and require Python 3.10+ in the Azure adapter's dependency file to match current support policy.
- Authenticate with DefaultAzureCredential via Managed Identity for Container Apps/Container Apps Jobs rather than account keys or connection strings, to satisfy the 'no plaintext secrets' acceptance criterion.
- Use BlobServiceClient.get_container_client()/get_blob_client() pattern rather than always constructing fresh clients from connection strings, since the build avoids hardcoded connection strings.
- If the retrieval handler is async (FastAPI), use azure.storage.blob.aio clients and add aiohttp as an explicit dependency; do not mix sync and async clients in the same module.
- When writing the storage adapter interface, wrap upload_blob/download_blob/list_blobs only — this is the minimal API surface needed to mirror the existing GCS adapter's behavior.
- Do not rely on StorageStreamDownloader being directly iterable for chunks; use `.chunks` explicitly per the 12.24.1 change to avoid silent behavior differences versus older SDK docs/tutorials.

**current version:** 12.31.1 (released 2026-10-29)

**api surface**
- pip install azure-storage-blob
- from azure.storage.blob import BlobServiceClient, ContainerClient, BlobClient
- BlobServiceClient(account_url=..., credential=DefaultAzureCredential())
- service.get_container_client(name) / service.get_blob_client(container, blob)
- blob_client.upload_blob(data, overwrite=...)
- blob_client.download_blob() -> StorageStreamDownloader; use .readall() or .chunks
- container_client.list_blobs()
- from azure.storage.blob.aio import BlobServiceClient (async variant, requires aiohttp)
- from azure.identity import DefaultAzureCredential

**pitfalls**
- 12.31.0 (2026-09-30) dropped Python 3.9 support; pipeline/base images must be on Python 3.10+.
- 12.27.0b1 (2025-06-12) previously dropped Python 3.8 support — ensure CI isn't still pinned to an older interpreter.
- 12.24.1 (2025-01-22) changed recommended stream-iteration pattern to StorageStreamDownloader.chunks instead of iterating the downloader directly.
- Async clients require installing a separate async HTTP transport (e.g., aiohttp); omitting it causes runtime errors, not import-time errors.
- BlobProperties objects as direct blob-name arguments were deprecated (12.19.0b1); older sample code using this pattern may silently misbehave on current versions.
- Client-side encryption v1.0 is deprecated in favor of v2.0 — avoid using require_encryption/encryption_version='1.0' in new code.

*As of: 2026-10-29 (azure-storage-blob 12.31.1); changelog history reviewed from 2024-05 through 2026-10*

**Sources**
- [azure-storage-blob · PyPI](https://pypi.org/project/azure-storage-blob/) (official-docs) -- "The latest stable release is 12.31.1, released October 29, 2026. pip install azure-storage-blob. Python 3.10 or later is required."
- [Azure Storage Blobs client library for Python | Microsoft Learn](https://learn.microsoft.com/en-us/python/api/overview/azure/storage-blob-readme?view=azure-python) (official-docs) -- "Python 3.10 or later is required to use this package... Four different clients are provided to interact with the various components of the Blob Service: BlobServiceClient, ContainerClient, BlobClient, BlobLeaseClient."
- [azure-sdk-for-python CHANGELOG.md (azure-storage-blob)](https://github.com/Azure/azure-sdk-for-python/blob/main/sdk/storage/azure-storage-blob/CHANGELOG.md) (official-docs) -- "Version 12.31.0 requires Python 3.10+. Python 3.9 is no longer supported. ... 12.24.1 (2025-01-22): to iterate over the blob data stream, use StorageStreamDownloader.chunks."


### Official documentation: azure-identity
*Find the OFFICIAL documentation for "azure-identity": its current stable version, how it is installed or enabled, the API surface this build will use, and any breaking changes or pitfalls in the last 2 years (prioritise 2025-2026 current Azure offerings).*

azure-identity is Microsoft's official Python auth library providing Entra ID (Azure AD) token credentials used across all Azure SDKs; current stable release is 1.27.0 (2026-10-26), installed via `pip install azure-identity`, now requiring Python 3.10+. For this build it supplies the credential object (DefaultAzureCredential / ManagedIdentityCredential) passed into the Key Vault secrets client and used to mint bearer tokens for Azure OpenAI/Foundry and optionally AAD-based Postgres Flexible Server auth, letting Container Apps use a user-assigned managed identity in place of GCP service-account JSON keys.

**Key findings**
- Current stable version: 1.27.0, released 2026-10-26 per PyPI and the official CHANGELOG.md (next entry after is 1.26.0, 2026-09-30).
- Install: `pip install azure-identity` (per Microsoft Learn identity-readme, ms.date 2026-10-26).
- Minimum Python support is now 3.10 (as of the 1.27.0-era docs); PR #49638 merged 2026-10-21 dropped Python 3.9 support, following the earlier 1.22.0 (2025-05-06) change that dropped Python 3.8.
- As of v1.14.0, DefaultAzureCredential's continuation policy changed: it now tries all developer credentials in the chain even after one fails, rather than stopping at the first failure (deployed/managed-identity credentials still stop the chain with an exception).
- v1.22.0 (2025-05-06) is a breaking change for Service Fabric managed identity: it now raises an exception if client_id or identity_config are set, instead of silently ignoring them (not applicable to Container Apps but documents the SDK's breaking-change cadence).
- v1.26.0b2 (2026-02-11, preview) renamed WorkloadIdentityCredential's `use_token_proxy` kwarg to `enable_azure_proxy`; this and the new AKS 'identity binding' feature (enable_azure_proxy=True) are AKS-specific and not relevant to Container Apps.
- Continuous Access Evaluation (enable_cae=True on get_token) is supported per-request since v1.14.0 but explicitly NOT supported for developer or managed-identity credentials.
- Async credentials (azure.identity.aio) must be explicitly closed (`await credential.close()` or used as an async context manager) to avoid leaking the underlying transport session.
- DEBUG-level logging (logging_enable=True) can expose request/response bodies; INFO-level logging is safe and does not include secrets, per the official troubleshooting guidance.
- Managed identity support is explicitly documented for App Service/Functions, Azure Arc, Cloud Shell, AKS, Service Fabric, and VMs/VMSS -- Container Apps managed identity is covered under the general DefaultAzureCredential/ManagedIdentityCredential chain, not called out as a separate bullet in this readme.

**Recommendations**
- Pin azure-identity>=1.24,<2 (or simply 1.27.0) in requirements/pyproject, and ensure CI/Container Apps base image runs Python 3.10+ since 3.8/3.9 are no longer supported.
- Use DefaultAzureCredential() as the single credential object across the Azure adapter layer: it will pick up Container Apps' managed identity in production and developer-tool credentials (Azure CLI, VS Code) locally, matching the 'swappable adapters' design goal.
- For a user-assigned managed identity on the Container App, pass managed_identity_client_id=... (or set AZURE_CLIENT_ID) to DefaultAzureCredential rather than relying on system-assigned identity resolution order.
- Wrap any async credential usage (if the FastAPI app uses azure.identity.aio for Key Vault/OpenAI async clients) in an async context manager or ensure .close() is called to avoid connection leaks under load.
- Do not set logging_enable=True in production; keep default INFO logging to avoid leaking secrets in logs, consistent with the no-plaintext-secrets acceptance criterion.
- If AAD-based Postgres Flexible Server auth is used instead of a static password, request a token with get_token('https://ossrdbms-aad.database.windows.net/.default') and refresh it per SQLAlchemy connection; otherwise use Key Vault-stored credentials via the secrets adapter -- decide and document this once, since it affects the DB adapter's token-refresh logic.
- Avoid WorkloadIdentityCredential's AKS-specific identity-binding API (enable_azure_proxy) -- it is preview, AKS-only, and not applicable to Container Apps/Container Apps Jobs.

**current version:** 1.27.0 (released 2026-10-26)

**api surface**
- from azure.identity import DefaultAzureCredential -- primary credential for prod (managed identity) and local dev chain
- DefaultAzureCredential(managed_identity_client_id=...) -- target a specific user-assigned managed identity on the Container App
- credential.get_token('<scope>/.default') -- raw token retrieval, e.g. for Azure OpenAI/Foundry or AAD Postgres auth
- from azure.identity import ManagedIdentityCredential -- direct managed-identity-only credential (no dev fallback)
- from azure.identity.aio import DefaultAzureCredential + await credential.close() / async with -- async variant for async FastAPI paths
- AzureAuthorityHosts / authority=... kwarg -- only needed if targeting a sovereign cloud, not expected for this build
- azure-identity-broker (optional package) -- only relevant for interactive/WAM auth, not used in server workloads

**pitfalls**
- Minimum Python raised to 3.10 as of the current docs/PR #49638 (merged 2026-10-21); 3.8 support ended at v1.22.0 (2025-05-06) -- verify Container Apps base image Python version.
- DefaultAzureCredential's error-continuation behavior changed at v1.14.0: it no longer stops at the first failed developer credential, which can mask misconfiguration if not tested against the real credential chain order.
- enable_cae=True is not supported for managed identity or developer credentials -- don't rely on CAE for the managed-identity path used in Container Apps.
- Async credentials leak their transport session if not closed -- must call close() or use as async context manager.
- logging_enable=True exposes request/response bodies at DEBUG level and must never be enabled in a production config that also has the no-plaintext-secrets requirement.
- WorkloadIdentityCredential's kwarg was renamed (use_token_proxy -> enable_azure_proxy) in a 1.26.0b2 preview tied to AKS identity bindings -- irrelevant to Container Apps but a trap if copying AKS-oriented sample code.

*As of: 2026-10-26 (per Microsoft Learn identity-readme ms.date and PyPI 1.27.0 release date)*

**Sources**
- [Azure Identity client library for Python | Microsoft Learn](https://learn.microsoft.com/en-us/python/api/overview/azure/identity-readme?view=azure-python) (official-docs) -- "Install Azure Identity with pip: pip install azure-identity ... Python 3.10 or a recent version of Python 3 (this library doesn't support end-of-life versions)"
- [azure-sdk-for-python CHANGELOG.md (azure-identity)](https://github.com/Azure/azure-sdk-for-python/blob/main/sdk/identity/azure-identity/CHANGELOG.md) (official-docs) -- "Service Fabric managed identity now raises exceptions if client_id or identity_config parameters are specified, whereas previously these were silently ignored."
- [azure-identity · PyPI](https://pypi.org/project/azure-identity/) (official-docs) -- "Current Stable Version: 1.27.0 ... Release Date: October 26, 2026"
- [[Identity] Drop Python 3.9 From Identity, add Python 3.15 #49638](https://github.com/Azure/azure-sdk-for-python/pull/49638) (repo) -- "Update pyproject.toml to drop python 3.9 and add python 3.15 ... merged on October 21, 2026"


### Official documentation: FastAPI
*Find the OFFICIAL documentation for "FastAPI": its current stable version, how it is installed or enabled, the API surface this build will use, and any breaking changes or pitfalls in the last 2 years (prioritise 2025-2026 current Azure offerings).*

FastAPI's official docs (fastapi.tiangolo.com) confirm the current stable release is 0.162.0 (PyPI, released 2026-10-23), requiring Python >=3.10 (3.10-3.14). Installation is via `pip install "fastapi[standard]"` or `uv add "fastapi[standard]"`, which pulls in uvicorn and the `fastapi` CLI (`fastapi dev` / `fastapi run`). This build will use the core API surface: `FastAPI()` app instance, `APIRouter`, path operation decorators, Pydantic v2 `BaseModel` request/response models, the `Depends()` dependency-injection system (for DB sessions and settings), `HTTPException`, and the `lifespan` async-context-manager pattern for startup/shutdown (replacing the deprecated `@app.on_event`). For Azure Container Apps, the docs' deployment-concepts page explicitly recommend running a single Uvicorn process per container and letting the cloud platform handle replication, which matches the planned container-based deployment.

**Key findings**
- Current stable version per PyPI and official release notes: 0.162.0, released 2026-10-23.
- FastAPI requires Python >=3.10; PyPI classifiers list 3.10, 3.11, 3.12, 3.13, 3.14 support.
- Install via `pip install "fastapi[standard]"` or `uv add "fastapi[standard]"`; the `[standard]` extra bundles uvicorn and the fastapi CLI.
- `fastapi dev` runs a local auto-reload dev server bound to 127.0.0.1; `fastapi run` is the production-mode command bound to 0.0.0.0 with auto-reload off.
- `@app.on_event("startup"/"shutdown")` is deprecated; official guidance is to use the `lifespan` async-context-manager parameter on the FastAPI() constructor instead -- mixing both is unsupported ('it's all lifespan or all events, not both').
- FastAPI follows 0.x versioning and ships frequent 'Breaking Changes' entries in minor releases (multiple breaking-change releases observed through 2025 into Oct 2026 per the official release-notes page), so pinning and reading release notes before upgrading matters.
- Official deployment-concepts docs recommend a single Uvicorn worker process per container for cloud platforms that handle replication themselves (directly applicable to Azure Container Apps).

**Recommendations**
- Pin an exact FastAPI version in requirements (e.g. 0.162.0) rather than a loose range, given the project's frequent breaking-change releases, and re-check the official release notes before any version bump during the migration.
- Use the `lifespan` async-context-manager pattern (not `@app.on_event`) for any startup/shutdown logic such as initializing the Postgres/pgvector engine or Azure clients, since on_event is deprecated.
- Keep request/response schemas on Pydantic v2 `BaseModel` (already implied by pydantic-settings usage) -- no FastAPI code change needed here beyond ensuring Pydantic v1-style validators aren't reintroduced.
- In the Container Apps Bicep/Dockerfile, run a single Uvicorn/FastAPI process per container (via `fastapi run` or direct uvicorn invocation) and let Container Apps handle replica scaling, per official deployment guidance -- avoid baking in `--workers` multiprocessing unless memory/CPU sizing is explicitly planned for it.
- Verify the Dockerfile's Python base image matches a FastAPI-supported version (>=3.10); do not target Python 3.9 or earlier.

**current version:** 0.162.0 (released 2026-10-23)

**api surface**
- FastAPI() app instance and APIRouter for route organization
- Path operation decorators (@app.get/post/put/delete) with async def handlers
- Pydantic v2 BaseModel for request/response schema validation
- Depends() dependency-injection system for DB session / settings / auth wiring
- HTTPException for error responses
- lifespan async-context-manager parameter for startup/shutdown (DB engine, Azure client init/teardown)
- fastapi[standard] extra pulling in uvicorn + fastapi CLI (`fastapi dev`, `fastapi run`)

**pitfalls**
- @app.on_event('startup'/'shutdown') is deprecated in favor of the lifespan context manager; mixing both is not supported
- FastAPI ships breaking changes inside 0.x minor version bumps (not reserved for major versions) -- release notes list multiple 'Breaking Changes' entries through 2025 and into Oct 2026, so blind upgrades risk regressions
- Current release requires Python >=3.10 -- any base image still on 3.8/3.9 will fail to install current FastAPI [uncertain: exact version where 3.8/3.9 support was dropped]
- Docs explicitly warn against running multiple Uvicorn worker processes per container on platforms (like Container Apps) that already replicate containers -- doing so can double memory usage for loaded models/clients

*As of: 2026-10-23 (FastAPI 0.162.0); page content fetched 2026-11-02*

**Sources**
- [FastAPI - Release Notes](https://fastapi.tiangolo.com/release-notes/) (official-docs) -- "0.162.0 ... Breaking Changes"
- [FastAPI (homepage) - requirements and installation](https://fastapi.tiangolo.com/) (official-docs) -- "uv add "fastapi[standard]" ... Make sure you put "fastapi[standard]" in quotes to ensure it works in all terminals."
- [fastapi on PyPI](https://pypi.org/project/fastapi/) (official-docs) -- "Requires: Python >=3.10"
- [FastAPI - Releases (GitHub)](https://github.com/fastapi/fastapi/releases) (repo) -- "0.162.0 ... boolean form fields handle omitted values"
- [FastAPI - Events: startup and shutdown](https://fastapi.tiangolo.com/advanced/events/) (official-docs) -- "The recommended way to handle the startup and shutdown is using the lifespan parameter of the FastAPI app ... It's all lifespan or all events, not both."
- [FastAPI - About FastAPI versions / Deployments - Concepts](https://fastapi.tiangolo.com/deployment/concepts/) (official-docs) -- "The cloud service will probably handle replication for you ... it would most probably be a single Uvicorn process, and the cloud service would be in charge of replicating it."
- [FastAPI CLI](https://fastapi.tiangolo.com/fastapi-cli/) (official-docs) -- "fastapi dev ... fastapi run"


### Official documentation: SQLAlchemy
*Find the OFFICIAL documentation for "SQLAlchemy": its current stable version, how it is installed or enabled, the API surface this build will use, and any breaking changes or pitfalls in the last 2 years (prioritise 2025-2026 current Azure offerings).*

SQLAlchemy 2.0 is the API style this build is locked to (per CLAUDE.md-equivalent build constraints: plain Python, pydantic-settings, SQLAlchemy 2.0). As of Nov 2026, the 2.0 line is in maintenance at 2.0.57 (released ~Nov 3, 2026) while 2.1 (currently 2.1.8) is the new active series; the official docs at docs.sqlalchemy.org/en/20/ explicitly label 2.0 'legacy' and point to /en/21/. Installation is `pip install SQLAlchemy` (async support via the bundled greenlet dependency, plus an asyncpg driver for Postgres). This build will use declarative `Mapped[]`/`mapped_column` models, `select()` + `Session.execute()`/`AsyncSession.execute()`, `create_async_engine('postgresql+asyncpg://...')`, and `Index(..., postgresql_using='hnsw', postgresql_with={...}, postgresql_ops={...})` for the pgvector HNSW index, matching the pgvector-python + Azure Postgres sample patterns found.

**Key findings**
- Latest SQLAlchemy release overall is 2.1.8 (PyPI, as of fetch date Nov 2026); the 2.0 series' latest point release is 2.0.57 (~Nov 3, 2026) and is now flagged 'legacy'/maintenance on docs.sqlalchemy.org/en/20/, with 2.1 as the current docs series.
- PyPI package requires Python >=3.11 for the latest build metadata shown, but the 2.0 docs intro page states the 2.0 series itself targets Python 3.7+ (cPython and PyPy) [uncertain] — version-specific requirement pages may have shifted since initial 2.0 release.
- Core 2.0 ORM pattern: `class Base(DeclarativeBase)` with `id: Mapped[int] = mapped_column(primary_key=True)` replacing the old `declarative_base()`/plain `Column()` style.
- Querying in 2.0 is unified around `select()` passed to `Session.execute()` (sync) or `AsyncSession.execute()` (async); the legacy `Query` object still works but is considered the old paradigm.
- Async support requires `sqlalchemy[asyncio]` (pulls in greenlet) plus an async DBAPI driver — `asyncpg` for Postgres; engine URL form is `postgresql+asyncpg://user:pass@host/db`.
- A single `AsyncSession` is not safe for concurrent tasks — each concurrent coroutine needs its own session; `expire_on_commit=False` is recommended to avoid implicit lazy I/O after commit, which async disallows by default.
- `relationship(lazy='dynamic')` is legacy in 2.0; replacement is `lazy='write_only'` requiring explicit `.select()` calls — relevant if this build adds any ORM relationships beyond simple columns.
- pgvector-python integrates with SQLAlchemy via `from pgvector.sqlalchemy import Vector` (or `VECTOR`), used as `mapped_column(Vector(768))` for this build's 768-dim column, matching the existing required `Vector(768)` type.
- HNSW index creation pattern confirmed from both pgvector-python README and an Azure-Samples repo (azure-postgres-pgvector-python): `Index(name, Model.col, postgresql_using='hnsw', postgresql_with={'m':16,'ef_construction':64}, postgresql_ops={'col':'vector_cosine_ops'})`.
- Some pgvector-python examples register the vector type via an SQLAlchemy `connect` event (`register_vector(dbapi_connection)`) for raw psycopg2 use; this may be unnecessary when using the dedicated `pgvector.sqlalchemy.Vector` column type with asyncpg — needs confirmation against the specific driver chosen [uncertain].

**Recommendations**
- Pin to the SQLAlchemy 2.0.x maintenance line (not 2.1) to match the build's explicit 'SQLAlchemy 2.0' constraint and avoid untested 2.1 behavior changes; verify exact pinned version against the current GCP codebase's requirements file.
- Use `Mapped[]`/`mapped_column` declarative style consistently if the existing models already use it; do not introduce the 2.1-only patterns during this migration.
- For Postgres on Azure Flexible Server, use `postgresql+asyncpg://` (or sync `psycopg`/`psycopg2` if the existing codebase is sync) — do not mix drivers without updating the engine URL scheme.
- Keep the pgvector `Vector(768)` column type and HNSW index definition exactly as in GCP (per acceptance criterion 6); only the connection/engine wiring should change for Azure.
- If async session usage is introduced, give each concurrent WhatsApp request handler its own `AsyncSession` instance and set `expire_on_commit=False` to avoid implicit-IO errors.
- Do not adopt `lazy='dynamic'` relationships if any are added; use `lazy='write_only'` per current 2.0 guidance.
- Call `await engine.dispose()` on shutdown in Container Apps to avoid connection leaks/errors on scale-down, consistent with SQLAlchemy's async engine lifecycle guidance.

**current version:** 2.0.57 (2.0 maintenance line, ~Nov 3, 2026); overall latest SQLAlchemy release is 2.1.8 (Nov 4, 2026) per PyPI — this build should target the pinned 2.0.x line per its stated constraint

**api surface**
- sqlalchemy.orm.DeclarativeBase / Mapped[] / mapped_column() for model definitions
- sqlalchemy.select() combined with Session.execute() (sync) or AsyncSession.execute() (async)
- sqlalchemy.ext.asyncio.create_async_engine('postgresql+asyncpg://...') and async_sessionmaker(engine, expire_on_commit=False)
- pgvector.sqlalchemy.Vector(768) column type for the embedding column
- sqlalchemy.Index(..., postgresql_using='hnsw', postgresql_with={'m':16,'ef_construction':64}, postgresql_ops={'col':'vector_cosine_ops'}) for the HNSW index
- engine.dispose() / await engine.dispose() for connection lifecycle cleanup in Container Apps

**pitfalls**
- 2.0 docs are now marked 'legacy' with 2.1 as current — pin exact version in requirements to avoid accidentally picking up 2.1 behavior changes during dependency resolution
- Declarative mapping requires DeclarativeBase + Mapped[] typing; mixing old Column()-only style with new Mapped[] style is allowed but loses type-checking benefits
- lazy='dynamic' relationship loading is legacy; use lazy='write_only' with explicit .select() calls instead
- AsyncSession instances must not be shared across concurrent tasks/requests — each request needs its own session
- Implicit lazy-load I/O is disallowed in async context by default; must eager-load (e.g. selectinload()) or it raises at runtime
- expire_on_commit=False recommended for async sessions to prevent unexpected re-query on attribute access after commit
- Old SQLAlchemy type-stub packages must be uninstalled when adopting 2.0's native typing, or type inference breaks [uncertain]

*As of: 2026-11-11 (page content observed dated up to Nov 4, 2026 release notes)*

**Sources**
- [SQLAlchemy 2.0 Documentation (en/20/)](https://docs.sqlalchemy.org/en/20/) (official-docs) -- "Release: 2.0.57 legacy version ... Version 2.1 is the Current Documentation"
- [SQLAlchemy 2.0 Changelog: What's New in SQLAlchemy 2.0?](https://docs.sqlalchemy.org/en/20/changelog/whatsnew_20.html) (official-docs) -- "Session raises proactively when illegal concurrent or reentrant access is detected"
- [SQLAlchemy asyncio extension docs](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html) (official-docs) -- "AsyncSession object is a standard Python object which ... is not safe for use in multiple, concurrent tasks"
- [SQLAlchemy 2.0 Intro / Installation](https://docs.sqlalchemy.org/en/20/intro.html#installation) (official-docs) -- "pip install SQLAlchemy ... SQLAlchemy now targets Python 3.7 and above"
- [SQLAlchemy on PyPI](https://pypi.org/project/SQLAlchemy/) (official-docs) -- "Version: 2.1.8 ... Development Status :: 5 - Production/Stable"
- [pgvector/pgvector-python GitHub repo](https://github.com/pgvector/pgvector-python) (repo) -- "class Item(Base): embedding: Mapped[list[float]] = mapped_column(VECTOR(3))"
- [azure-postgres-pgvector-python example (sqlalchemy_movies.py)](https://github.com/Azure-Samples/azure-postgres-pgvector-python/blob/main/examples/sqlalchemy_movies.py) (repo) -- "postgresql_using="hnsw", postgresql_with={"m": 16, "ef_construction": 64}, postgresql_ops={"title_vector": "vector_cosine_ops"}"


### Official documentation: pydantic-settings
*Find the OFFICIAL documentation for "pydantic-settings": its current stable version, how it is installed or enabled, the API surface this build will use, and any breaking changes or pitfalls in the last 2 years (prioritise 2025-2026 current Azure offerings).*

pydantic-settings is the official, separately-distributed package providing BaseSettings for Pydantic v2 (it was split out of core pydantic). Install via `pip install pydantic-settings`; the API the build needs (BaseSettings, SettingsConfigDict with env_file/env_nested_delimiter/secrets_dir/env_prefix, and the settings_customise_sources hook) has been stable since pydantic-settings 2.x and is documented on the official pydantic.dev site. Notably, the library ships a built-in AzureKeyVaultSettingsSource, which is directly usable for the planned Azure secrets adapter. The main breaking change in the last 2 years is the v2.16.0 bump to require Python 3.11+ and python-dotenv>=1.2.2 (security fix), plus alias-resolution behavior changes.

**Key findings**
- pydantic-settings is a standalone PyPI package (not part of core pydantic) — required separately since pydantic v2.0; `from pydantic import BaseSettings` no longer works under pydantic v2.
- Official docs confirm install command: `pip install pydantic-settings` (pydantic.dev/docs/validation/latest/concepts/pydantic_settings).
- PyPI project page reports current version 2.16.2 [uncertain — exact release date conflicted between sources, see below].
- GitHub releases listing (as fetched) shows v2.16.1 and v2.16.0 as the most recent entries visible, with v2.16.0 requiring Python 3.11+ and python-dotenv>=1.2.2 (CVE mitigation), and changing alias-ignore behavior when validate_by_alias=False [uncertain — dates shown by the two fetches for the same version numbers disagreed, so exact release dates are not reliable].
- v2.15.0 made case_sensitive apply to init kwargs and config-file sources (previously only env vars).
- v2.14.2 was a security patch preventing symlink-following in the nested secrets settings source (relevant to secrets_dir usage).
- Source priority order (official docs): init settings > environment variables > dotenv file > secrets_dir file > custom sources (environment overrides dotenv; dotenv overrides secrets file).
- Official docs confirm a built-in AzureKeyVaultSettingsSource(settings_cls, vault_url, credential) that reads secrets from Azure Key Vault and can be composed via settings_customise_sources, with options to convert dash/kebab-case secret names to snake_case field names.
- settings_customise_sources(cls, init_settings, env_settings, dotenv_settings, file_secret_settings) is the official extension point for adding/reordering custom sources such as AzureKeyVaultSettingsSource.

**Recommendations**
- Pin pydantic-settings>=2.x (2.16+ family) and verify the project's Python runtime is >=3.11 before upgrading past 2.16.0, since that version raised the minimum Python requirement.
- Use SettingsConfigDict(env_file='.env', env_nested_delimiter='__', case_sensitive=False) to keep parity with the existing plain-pydantic-settings style already used in the codebase.
- For the Azure secrets adapter, use the official AzureKeyVaultSettingsSource wired in via settings_customise_sources rather than hand-rolling Key Vault calls — this keeps the storage/secrets abstraction swappable per the build's adapter pattern.
- If currently on python-dotenv <1.2.2, upgrade it alongside any pydantic-settings bump >=2.16.0 to pick up the CVE fix noted in that release.
- Re-check any field aliases after upgrading to 2.16.0+: the alias-ignore behavior under validate_by_alias=False changed and could silently stop env vars from populating aliased fields — add/adjust a settings test to confirm.
- Do not rely on secrets_dir with symlinked secret files on older pydantic-settings (<2.14.2); upgrade past that patch if using file-based secrets mounts (e.g., Container Apps secret volumes).

**current version:** 2.16.2 [uncertain — exact release date not independently confirmed; two fetches of version history gave inconsistent dates]

**api surface**
- BaseSettings (subclass for app config; replaces pydantic v1's built-in BaseSettings)
- SettingsConfigDict(env_file, env_prefix, env_nested_delimiter, secrets_dir, case_sensitive)
- model_config = SettingsConfigDict(...) on settings classes
- settings_customise_sources(cls, init_settings, env_settings, dotenv_settings, file_secret_settings) classmethod for adding/reordering sources
- PydanticBaseSettingsSource base class for custom sources
- AzureKeyVaultSettingsSource(settings_cls, vault_url, credential, snake_case_conversion=True) for Key Vault-backed secrets
- Default source priority: init > env vars > dotenv file > secrets_dir file > custom sources

**pitfalls**
- pydantic-settings is a separate package from core pydantic (post pydantic v2.0) — any legacy `from pydantic import BaseSettings` import will break and must be migrated (older than 2-year window but still a common gotcha when porting code).
- v2.16.0 raises minimum Python to 3.11+ — check runtime compatibility before bumping the pin in Container Apps base image.
- v2.16.0 mandates python-dotenv>=1.2.2 for a security fix; older dotenv pins may conflict.
- v2.16.0 changed alias resolution: aliases are ignored across all sources when validate_by_alias=False, which can silently break env-var-driven aliased fields after upgrade.
- v2.15.0 extended case-insensitive matching to init kwargs and config-file sources, a subtle behavior change for any code relying on case-sensitive init overrides.
- v2.14.2 was a security patch for symlink-following in secrets_dir/NestedSecretsSettingsSource — ensure any Container Apps secret-mount approach is on a patched version.
- GitHub vs PyPI version/date reporting was inconsistent across fetches in this research session — treat exact release dates with caution and re-verify directly against the official changelog before relying on a specific date.

*As of: PyPI listing fetched 2026-11-02, reporting current version 2.16.2; exact release date for that version is [uncertain] due to conflicting fetch results*

**Sources**
- [pydantic-settings · PyPI](https://pypi.org/project/pydantic-settings/) (official-docs) -- "Current Version: 2.16.2 — pip install pydantic-settings"
- [Settings Management - Pydantic](https://pydantic.dev/docs/validation/latest/concepts/pydantic_settings/) (official-docs) -- "pip install pydantic-settings ... SettingsConfigDict ... env_prefix, env_file, env_nested_delimiter, secrets_dir ... AzureKeyVaultSettingsSource(settings_cls, os.environ['AZURE_KEY_VAULT_URL'], DefaultAzureCredential())"
- [pydantic-settings Releases · GitHub](https://github.com/pydantic/pydantic-settings/releases) (repo) -- "pydantic-settings now requires Python 3.11+ ... python-dotenv>=1.2.2 ... Aliases are ignored in every source when validate_by_alias=False"


### Official documentation: gunicorn
*Find the OFFICIAL documentation for "gunicorn": its current stable version, how it is installed or enabled, the API surface this build will use, and any breaking changes or pitfalls in the last 2 years (prioritise 2025-2026 current Azure offerings).*

Gunicorn is the production WSGI/ASGI process manager that will run the FastAPI app inside the Azure Container Apps container, using Uvicorn worker processes for async support. Current stable is v26.2.x (2026), installed via `pip install gunicorn`, with the app launched as `gunicorn app.main:app -k uvicorn_worker.UvicornWorker -w <N> -b 0.0.0.0:<port>`. The main breaking-change risk for this build is that the classic `uvicorn.workers.UvicornWorker` import path is deprecated in favor of the standalone `uvicorn-worker` package, and `forwarded_allow_ips` handling changed in 24.1.0/24.1.1 in a way that briefly broke Uvicorn interop. Official docs site structure also changed (docs.gunicorn.org now redirects to gunicorn.org with a reorganized settings reference).

**Key findings**
- Current stable gunicorn version is 26.2.2 (released 2026-09-06, per PyPI/web search); PyPI classifiers show Python >=3.10 support (3.10-3.13) [uncertain]
- docs.gunicorn.org/en/stable/ and /en/latest/ both 301-redirect to gunicorn.org; the old settings.html path 404s — the current official settings reference is https://gunicorn.org/reference/settings/
- Install: `pip install gunicorn` (confirmed on official homepage gunicorn.org)
- Official homepage confirms explicit FastAPI/Starlette compatibility and lists worker types: Sync (default), Async (Gevent/Eventlet), Threads (gthread), and ASGI for native asyncio
- Default bind is 127.0.0.1:8000; default workers=1 (respects WEB_CONCURRENCY env var); default worker_class=sync; default timeout=30s; default forwarded_allow_ips='127.0.0.1,::1' (CIDR notation supported since 24.1.0)
- v24.1.0 added Docker images, PROXY protocol v2, CIDR support for forwarded_allow_ips; v24.1.1 shipped promptly after to fix a backward-compat regression where forwarded_allow_ips/proxy_allow_ips no longer returned plain strings, breaking tools expecting the old format including Uvicorn interop
- Since uvicorn 0.30.0 (2024-05-28), `uvicorn.workers.UvicornWorker` is deprecated in favor of the standalone `uvicorn-worker` PyPI package providing `uvicorn_worker.UvicornWorker` (and `UvicornH11Worker` for PyPy); the legacy import still works with a DeprecationWarning as of uvicorn 0.35.0 (~mid-2025) but is not yet removed [uncertain: exact current uvicorn removal timeline]
- 26.x line reportedly added HTTP/2 (beta, requires TLS + h2 library), a 'dirty arbiters' feature, and a control socket for runtime management via `gunicornc` [uncertain: not independently verified on an official changelog page, sourced via WebFetch summarization of gunicorn.org/reference/settings/]
- ssl_version setting is deprecated in favor of ssl_context per the settings reference

**Recommendations**
- Pin gunicorn in requirements (e.g. `gunicorn>=23,<27` or exact pin) and add `uvicorn-worker` as an explicit dependency rather than relying on the deprecated `uvicorn.workers.UvicornWorker` import, to avoid future-removal breakage
- Launch command for the Container Apps container: `gunicorn app.main:app -k uvicorn_worker.UvicornWorker -w ${WEB_CONCURRENCY:-2} -b 0.0.0.0:8000 --timeout 30 --graceful-timeout 30`
- If deployed behind Azure Container Apps' ingress/front door, explicitly set `forwarded_allow_ips` to the known private/internal proxy range rather than '*', given the 24.1.0/24.1.1 history around this setting and its security implications
- Do not use the old settings.html doc path in any internal docs/RUNBOOK; link to https://gunicorn.org/reference/settings/ instead since the old docs.gunicorn.org path now 404s
- Verify gunicorn + uvicorn_worker version pins at implementation time against the official PyPI changelog page directly (not just search-summarized text) before finalizing the Bicep/container image, since some 26.x feature claims above are summarizer-derived rather than independently confirmed on a primary changelog

**current version:** 26.2.2 (released 2026-09-06) [uncertain: derived from search summary, not an opened official PyPI release-history page with exact changelog entry]

**api surface**
- CLI launch: gunicorn <module>:<app> -k uvicorn_worker.UvicornWorker -w <workers> -b <host:port>
- worker_class / -k: uvicorn_worker.UvicornWorker (ASGI, for FastAPI) instead of deprecated uvicorn.workers.UvicornWorker
- workers / -w (also honors WEB_CONCURRENCY env var)
- bind / -b (host:port, unix:PATH, or fd://FD)
- timeout, graceful_timeout (worker liveness and SIGTERM grace period)
- forwarded_allow_ips, secure_scheme_headers (for correct https scheme detection behind Container Apps ingress)
- max_requests (worker recycling to bound memory growth)
- config file (-c gunicorn.conf.py) for centralizing the above instead of long CLI flags

**pitfalls**
- uvicorn.workers.UvicornWorker deprecated since uvicorn 0.30.0 (2024-05-28) in favor of the separate uvicorn-worker package; still importable with a DeprecationWarning as of 0.35.0 but should not be relied on long-term
- gunicorn 24.1.0 introduced a forwarded_allow_ips/proxy_allow_ips format regression breaking Uvicorn-adjacent tooling, fixed in the immediate 24.1.1 patch — always pin to >=24.1.1 if using any 24.x line
- Official docs moved: docs.gunicorn.org/en/stable and /en/latest now 301-redirect to gunicorn.org, and the old settings.html path returns 404 — use gunicorn.org/reference/settings/ going forward
- ssl_version setting deprecated in favor of ssl_context

*As of: 2026-11 (gunicorn 26.2.2, released 2026-09-06); uvicorn deprecation note current as of uvicorn 0.35.0 (~2025-06)*

**Sources**
- [Gunicorn homepage](https://gunicorn.org/) (official-docs) -- "Battle-tested. Production-ready. One command to serve your Python apps... Compatible with Django, Flask, FastAPI, Pyramid, Starlette, Falcon, and Bottle"
- [Gunicorn Settings reference](https://gunicorn.org/reference/settings/) (official-docs) -- "bind - The socket to bind (default: 127.0.0.1:8000)... worker_class - Type of workers to use (default: sync)... ssl_version is deprecated; use ssl_context instead"
- [gunicorn on PyPI](https://pypi.org/project/gunicorn/) (official-docs) -- "Current Stable Version: 26.2.0... Python Support: Python >=3.10"
- [Gunicorn 24.1.0 has been released (GitHub Discussion)](https://github.com/benoitc/gunicorn/discussions/3455) (repo) -- "24.1.1 is now available with a fix for backward compatibility with tools like uvicorn, specifically mentioning problems with tools expecting string values from forwarded_allow_ips or proxy_allow_ips settings"
- [uvicorn-worker (Kludex/uvicorn-worker)](https://github.com/Kludex/uvicorn-worker) (repo) -- "gunicorn example:app -w 4 -k uvicorn_worker.UvicornWorker ... For PyPy-compatible configurations, use uvicorn_worker.UvicornH11Worker instead"
- [[Bug]: uvicorn.workers.UvicornWorker deprecated · Issue #12069](https://github.com/BerriAI/litellm/issues/12069) (forum) -- "Since uvicorn 0.30.0, this worker is deprecated in favor of the uvicorn-worker package... the legacy import still works (with a DeprecationWarning)"


### Official documentation: uvicorn
*Find the OFFICIAL documentation for "uvicorn": its current stable version, how it is installed or enabled, the API surface this build will use, and any breaking changes or pitfalls in the last 2 years (prioritise 2025-2026 current Azure offerings).*

Uvicorn is the ASGI server this FastAPI bot runs on, confirmed via PyPI and the project's own GitHub docs (encode/uvicorn). Current stable is 0.54.0, installed with `pip install 'uvicorn[standard]'` for uvloop/httptools/websockets extras. The build will use the CLI entrypoint (`uvicorn app:app --host 0.0.0.0 --port 8000`) or `uvicorn.run()`, plus `--proxy-headers`/`--forwarded-allow-ips` for Azure Container Apps' front-door proxy. Recent versions dropped Python 3.8 (0.34.0) and Python 3.9 (0.40.0) support and changed default WebSocket implementation and startup-failure exit codes, which matter for container health checks.

**Key findings**
- Current stable version is 0.54.0 per PyPI package metadata (pypi.org/pypi/uvicorn/json) and the encode/uvicorn GitHub release notes.
- Install: `pip install uvicorn` (minimal) or `pip install 'uvicorn[standard]'` (adds uvloop, httptools, websockets, watchfiles, python-dotenv, PyYAML) per README.md.
- CLI usage: `uvicorn example:app` serves an ASGI callable `app(scope, receive, send)`; default bind is 127.0.0.1:8000 unless --host/--port given.
- `--workers` (default from $WEB_CONCURRENCY or 1) is incompatible with `--reload`; relevant for Container Apps scaling vs in-process workers.
- `--proxy-headers` (on by default) honors X-Forwarded-Proto/X-Forwarded-For only from IPs listed in `--forwarded-allow-ips` (default 127.0.0.1, ::1) [uncertain].
- v0.34.0 (per release notes) dropped Python 3.8 support; v0.40.0 dropped Python 3.9 support -- both [uncertain] on exact dates due to conflicting date strings across tool summaries.
- v0.50.0 changed default `--ws auto` resolution to the `websockets-sansio` implementation and deprecated the legacy `websockets` implementation [uncertain].
- v0.50.0 also changed behavior to exit with dedicated code 3 on any startup failure, which can affect orchestrator/health-check logic [uncertain].
- v0.53.0 introduced experimental HTTP/2 support [uncertain exact version/date due to conflicting fetch summaries].
- SSL options (`--ssl-keyfile`, `--ssl-certfile`, `--ssl-ca-certs`, `--ssl-ciphers`) exist but are typically unneeded on Container Apps since Azure terminates TLS at the ingress.

**Recommendations**
- Install with the `standard` extra (`uvicorn[standard]`) in the container image for uvloop/httptools performance, matching current FastAPI defaults.
- Run a single uvicorn process per container and rely on Container Apps replica scaling rather than uvicorn's own `--workers`, to keep restart/health semantics simple.
- Enable `--proxy-headers` and set `--forwarded-allow-ips='*'` (or the Container Apps internal proxy CIDR) so X-Forwarded-Proto/For from the platform ingress is trusted correctly.
- Pin a Python version >= 3.10 in the Dockerfile since recent uvicorn releases have dropped 3.8 and 3.9 support.
- Do not use `--reload` in the production container image; only use it for local dev.
- Avoid relying on experimental HTTP/2 (`--http h2`/zttp) given its experimental status; keep default HTTP/1.1 for the retrieval API.

**current version:** 0.54.0

**api surface**
- CLI: uvicorn <module>:<app> --host 0.0.0.0 --port 8000
- ASGI app callable: async def app(scope, receive, send)
- uvicorn.run(app, host=..., port=...) programmatic entrypoint
- --workers (process count; not combinable with --reload)
- --proxy-headers / --forwarded-allow-ips (trust upstream proxy headers)
- --log-level (critical|error|warning|info|debug|trace)
- --ssl-keyfile / --ssl-certfile / --ssl-ca-certs / --ssl-ciphers (likely unused since Container Apps terminates TLS)

**pitfalls**
- Python 3.8 support dropped (reported as v0.34.0) and Python 3.9 support dropped (reported as v0.40.0) [uncertain exact dates] -- base image must use a supported Python version.
- --workers cannot be combined with --reload; plan container entrypoint accordingly.
- Default --ws implementation switched to websockets-sansio starting v0.50.0, with the legacy websockets implementation deprecated [uncertain].
- Since v0.50.0, uvicorn exits with code 3 specifically on startup failure, which can change how Container Apps/health probes interpret crash-loop vs normal exit [uncertain].
- HTTP/2 support is experimental and requires an extra dependency (zttp per release notes); do not treat as production-ready [uncertain].
- Conflicting/garbled release dates across fetched sources for the same version numbers indicate the fetch summarizer may be unreliable on exact dates -- version numbers were corroborated across two sources, dates were not.

*As of: 0.54.0, per pypi.org/pypi/uvicorn/json and encode/uvicorn docs/release-notes.md (fetched 2026-11-02); exact release date varied across tool summaries (Sept 2024 vs Dec 2024 vs Sept 2026) and could not be independently pinned down, so treat as [uncertain]*

**Sources**
- [uvicorn · PyPI JSON API](https://pypi.org/pypi/uvicorn/json) (official-docs) -- "Version: "0.54.0" ... described as "The lightning-fast ASGI server.""
- [uvicorn PyPI project page](https://pypi.org/project/uvicorn/) (official-docs) -- "pip install uvicorn ... pip install 'uvicorn[standard]'"
- [encode/uvicorn README.md (raw)](https://raw.githubusercontent.com/encode/uvicorn/master/README.md) (official-docs) -- "uvicorn example:app ... Uvicorn supports HTTP/1.1, HTTP/2 and WebSockets."
- [encode/uvicorn release notes (raw)](https://raw.githubusercontent.com/encode/uvicorn/master/docs/release-notes.md) (official-docs) -- "Drop support for Python 3.9 ... Exit with the dedicated code 3 on any startup failure"
- [encode/uvicorn settings docs (fetched via raw markdown)](https://raw.githubusercontent.com/encode/uvicorn/master/docs/settings.md) (official-docs) -- "--proxy-headers: Enable/disable X-Forwarded-Proto and X-Forwarded-For headers ... --forwarded-allow-ips"
- [encode/uvicorn releases (GitHub)](https://github.com/encode/uvicorn/releases) (official-docs) -- "Introduces experimental HTTP/2 support via zttp ... Requires websockets>=13.0"


### Current Azure OpenAI/Foundry models (Nov 2026)
*Which current chat/vision models support structured JSON output and a thinking/reasoning budget equivalent, with pricing?*

For this build, chat/vision structured JSON output ('response_format'/'text.format' with strict JSON Schema) is officially supported on gpt-5.1, gpt-5.1-chat, gpt-5.1-codex, gpt-5-pro, gpt-5-codex, gpt-5/mini/nano, gpt-4.1 family, gpt-4o/mini, o3, o3-mini, o3-pro, o4-mini, and o1 (confirmed on Microsoft's structured-outputs doc, not yet listing GPT-6). A separate Microsoft Foundry doc (newer, Oct 2026) describes GPT-6 Astra/Sol/Luna and GPT-5.6/5.5/5.4 as reasoning models supporting a 'reasoning_effort' parameter (minimal/low/medium/high/xhigh/max) plus a GPT-5.6-only 'mode' (standard/pro) switch, and states these also support structured outputs, tools, and vision input. Azure OpenAI's embeddings REST API officially supports a 'dimensions' integer parameter (min 1) on text-embedding-3-small/large, which is how the build gets a 768-dim vector to match the existing pgvector column. Global Standard pricing per 1M tokens: GPT-5 $1.25/$10, GPT-6 Astra $10/$50, GPT-6 Sol $2/$10, GPT-6 Luna $0.10/$0.50, o3 $2/$8, o4-mini $1.10/$4.40, o1 $15/$60, text-embedding-3-small ~$0.022/1M, text-embedding-3-large ~$0.143/1M.

**Key findings**
- Official 'Supported models' list for structured outputs (learn.microsoft.com /azure/foundry/openai/how-to/structured-outputs, ms.date 2026-08-24) includes gpt-5.1 (2025-11-13), gpt-5.1-chat, gpt-5.1-codex[-mini], gpt-5-pro (2025-10-06), gpt-5-codex, gpt-5/mini/nano (2025-08-07), o3-pro, o3-mini, o1, gpt-4o/mini, gpt-4.1/mini/nano, o4-mini, o3; GPT-6 is absent from this specific list.
- Structured outputs is NOT supported with Bring-your-own-data, Assistants/Foundry Agents Service, or gpt-audio/gpt-audio-mini; schemas allow up to 100 properties and 5 nesting levels and require additionalProperties:false and all fields required.
- A newer Microsoft Foundry doc (learn.microsoft.com /azure/foundry/openai/how-to/reasoning, ms.date 2026-10-23) covers GPT-6 Astra and GPT-5 reasoning models; per my fetch, reasoning_effort (none/minimal/low/medium/high/xhigh/max) applies to GPT-6, GPT-5 series, and o-series except o1-mini, and a GPT-5.6-only 'mode' (standard vs. higher-cost/latency 'pro') is independent of reasoning_effort.
- Exact per-model-family allowed values for reasoning_effort/mode (e.g. whether 'max' is GPT-6/5.6-only and 'minimal' is legacy-GPT-5-only) vary between my own page fetch and a separate search-engine summary of the same page, so the fine-grained matrix is not fully reconciled.
- Azure OpenAI embeddings REST reference (learn.microsoft.com /rest/api/microsoft-foundry/azureopenai/embeddings, ms.date 2026-05-27) documents a 'dimensions' integer request parameter, min 1, 'Only supported in text-embedding-3 and later models' -- this is the mechanism for producing a 768-dim vector.
- Embedding limits (learn.microsoft.com /azure/foundry/openai/how-to/embeddings, ms.date 2026-07-22): 8,192 max input tokens per item, max 2,048 items per array, 300,000-token aggregate cap per request.
- Azure's official pricing page (azure.microsoft.com/.../openai-service), fetched directly, rendered blank '$-' placeholders (likely JS-rendered table); the same page fetched via a text-rendering proxy returned concrete Global/Standard figures matching independent third-party trackers (cloudzero.com, finout.io, tech-insider.org): GPT-5 $1.25/$10 per 1M in/out, GPT-6 Astra $10/$50 (short context) and $20/$75 (long), GPT-6 Sol $2/$10 (short)/$4/$15 (long), GPT-6 Luna $0.10/$0.50 (short)/$0.20/$0.75 (long), o3 $2/$8, o4-mini $1.10/$4.40, o1 $15/$60, text-embedding-3-small $0.000022/1K, text-embedding-3-large $0.000143/1K.

**Recommendations**
- Use a GPT-5/5.x or gpt-4.1/4o-family chat model (confirmed on the official structured-outputs model list) for the JSON-structured answer path rather than GPT-6, until Microsoft's structured-outputs doc explicitly lists GPT-6 as supported.
- For reasoning/thinking-budget control, use the 'reasoning_effort' parameter (values minimal/low/medium/high) on a GPT-5-series or o-series deployment; avoid depending on 'xhigh'/'max'/'mode' until the exact per-model support matrix is reconfirmed against a second primary source.
- For the embedding model, deploy text-embedding-3-small or text-embedding-3-large and pass 'dimensions: 768' in the embeddings request body to match the existing pgvector Vector(768) column and HNSW index unchanged.
- Treat the Global/Standard price list as indicative only (pricing is account/region/negotiated-discount dependent and the official page didn't render static values for me); confirm current rates in the Azure Pricing Calculator before finalizing the cost-cap breaker config.
- Budget for GPT-6 Astra/Sol or o-series costing far more per output token (up to $50-$75/1M) than GPT-6 Luna or text-embedding models; keep the cost-cap breaker test using the cheapest deployed model's published rate, not an assumed one.

*As of: Nov 2026; source docs dated 2026-10-23 (reasoning), 2026-08-24 (structured outputs), 2026-07-22 (embeddings how-to), 2026-05-27 (REST reference), pricing page accessed 2026-11-02*

**Sources**
- [How to use structured outputs with Azure OpenAI in Microsoft Foundry Models](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/structured-outputs) (official-docs) -- "Supported models ... gpt-5.1 version: 2025-11-13 ... gpt-5-mini version 2025-08-07 ... API version 2024-08-01-preview is the first version that supports structured outputs."
- [Azure OpenAI reasoning models - GPT-6 Astra and GPT-5 - Microsoft Foundry](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/reasoning) (official-docs) -- "mode ... Available exclusively for gpt-5.6 models in the Responses API ... Standard (default) ... Pro: aggregates the work it performs into a single answer"
- [Generate embeddings with Azure OpenAI - Microsoft Foundry](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/embeddings) (official-docs) -- "The maximum input length for the current embedding models is 8,192 tokens ... the maximum array size is 2,048 ... 300,000-token aggregate limit"
- [Microsoft Foundry REST Reference - Azure OpenAI - Embeddings](https://learn.microsoft.com/en-us/rest/api/microsoft-foundry/azureopenai/embeddings) (official-docs) -- "dimensions | integer | The number of dimensions the resulting output embeddings should have. Only supported in text-embedding-3 and later models. Constraints: min: 1"
- [Truncate Dimensions - Azure AI Search](https://learn.microsoft.com/en-us/azure/search/vector-search-how-to-truncate-dimensions) (official-docs) -- "text-embedding-3 models are retrained on the Matryoshka Representation Learning (MRL) technique that produces multiple vector representations at different levels of compression."
- [Azure OpenAI Service Pricing](https://azure.microsoft.com/en-us/pricing/details/cognitive-services/openai-service/) (official-docs) -- "GPT-6 Astra (short context) - Input: $10 - Output: $50 ... GPT-6 Luna (short context) - Input: $0.10 - Output: $0.50"


### Structured JSON output on Azure OpenAI
*How to enforce response_schema/JSON-mode and vision inputs via Azure OpenAI SDK to replace google-genai response_schema?*

Azure OpenAI's Chat Completions API (and the newer Responses API) support strict JSON Schema structured outputs natively via response_format={type:'json_schema', json_schema:{..., strict:true}}, or more simply via the Python SDK's client.beta.chat.completions.parse(response_format=PydanticModel) -- this is the direct 1:1 replacement for google-genai's response_schema. Minimum API version is 2024-08-01-preview (also available on the GA /openai/v1/ surface). Azure enforces a stricter JSON Schema subset than raw OpenAI (additionalProperties:false, all fields required, no minLength/pattern/minimum/etc., max 100 properties / 5 nesting levels). Vision input uses the OpenAI-standard message shape with an image_url content block (base64 data URI or remote URL); combining vision with structured outputs on a gpt-4o-2024-08-06+ deployment appears to be supported per a Microsoft blog title, but this combination and the exact vision message shape could not be independently confirmed from a fully-read primary source this session.

**Key findings**
- response_format={'type':'json_schema','json_schema':{'name':...,'strict':true,'schema':{...}}} works unchanged on Azure OpenAI Chat Completions and Responses APIs; confirmed by fully reading learn.microsoft.com 'How to use structured outputs with Azure OpenAI', page dated 2026-08-24.
- Python SDK shortcut: client.beta.chat.completions.parse(model=DEPLOYMENT_NAME, messages=[...], response_format=PydanticModel) returns completion.choices[0].message.parsed; Microsoft's tested versions were openai 1.42.0 / pydantic 2.8.2.
- Responses API equivalent (OpenAI Python 2.x): openai.responses.parse(model=..., input=..., text_format=PydanticModel) -> response.output_parsed.
- Minimum API version for structured outputs is 2024-08-01-preview; also supported on the GA /openai/v1/ endpoint surface.
- Azure's JSON Schema subset requires additionalProperties:false and every property listed under required (optional fields must be emulated with a nullable union type, e.g. ['string','null']); unsupported keywords include minLength/maxLength/pattern/format for strings, minimum/maximum/multipleOf for numbers, and minItems/maxItems/uniqueItems for arrays.
- Schema limits: max 100 total object properties, max 5 levels of nesting; the root schema cannot be type anyOf; $defs and recursive $ref schemas are explicitly supported.
- parallel_tool_calls must be set to false when combining structured outputs with function/tool calling, per the same doc.
- Supported-models list (doc dated 2026-08-24) includes gpt-4o-2024-08-06, gpt-4o-2024-11-20, gpt-4o-mini-2024-07-18, the gpt-4.1 family, o1/o3/o4-mini, and the gpt-5 family; explicitly NOT supported for Bring-your-own-data, Assistants/Foundry Agents Service, or gpt-audio/gpt-audio-mini models.
- [uncertain] Vision input appears to use the OpenAI-compatible shape {'type':'image_url','image_url':{'url':'data:image/<mime>;base64,<data>'}} with an optional 'detail' (low/high/auto) field -- seen only in search-engine summaries of the official gpt-with-vision doc; repeated attempts to fetch the page body this session returned only front-matter metadata, so the exact code sample was not independently read.
- [uncertain] A Microsoft Tech Community post titled 'Introducing GPT-4o-2024-08-06 API with Structured Outputs on Azure' implies gpt-4o-2024-08-06 can combine multimodal image input with json_schema structured outputs for extracting structured data from images, but the fetch tool returned only the page title, not the body or code sample, so this combination is not independently confirmed from a fully-read primary source.

**Recommendations**
- Replace google-genai's response_schema with response_format={'type':'json_schema','json_schema':{'name':...,'strict':true,'schema':...}} on chat.completions.create, or the more ergonomic client.beta.chat.completions.parse(response_format=PydanticModel) path, as the direct equivalent.
- Write every Pydantic/JSON schema with additionalProperties=False and all fields required (model optional fields as nullable unions, not omitted keys) to satisfy Azure's stricter JSON Schema subset.
- Pin the Azure OpenAI API version to 2024-08-01-preview or later (or move to the /openai/v1/ GA endpoint) before relying on structured outputs.
- Deploy a gpt-4o-2024-08-06 (or newer gpt-4.1/gpt-5 family) snapshot specifically, since structured outputs are not available on every deployed model version.
- Set parallel_tool_calls=False whenever structured outputs are combined with function/tool calling.
- [uncertain] For the OCR/vision extraction path, prototype sending the scanned-paper image as a base64 data-URI image_url content block alongside response_format json_schema on a gpt-4o-2024-08-06+ deployment, and verify this combination empirically as part of the OCR A/B gate, since it was not confirmed from a fully-read primary source this session.
- Disregard older forum/Q&A reports claiming gpt-4o-mini lacks json_schema support -- the current Microsoft Learn page (checked 2026-08-24) lists gpt-4o-mini-2024-07-18 as a supported model.

*As of: Primary source fully read: Microsoft Learn 'How to use structured outputs with Azure OpenAI' page, ms.date 2026-08-24 (structured outputs / JSON schema facts). The gpt-with-vision page carries ms.date 2026-07-29 per its metadata, but its body could not be fully retrieved this session, so vision-specific facts rely on secondary search summaries of that same page.*

**Sources**
- [How to use structured outputs with Azure OpenAI in Microsoft Foundry Models](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/structured-outputs) (official-docs) -- "response_format is set to json_schema with strict: true set... Structured outputs are not supported with parallel function calls. When using structured outputs set parallel_tool_calls to false."
- [How to use vision-enabled chat models - Microsoft Foundry](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/gpt-with-vision) (official-docs) -- "Learn how to use vision-enabled chat models in Azure OpenAI, including how to call the Chat Completion API and process images."
- [Introducing GPT-4o-2024-08-06 API with Structured Outputs on Azure](https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/introducing-gpt-4o-2024-08-06-api-with-structured-outputs-on-azure/4232684) (article) -- "Introducing GPT-4o-2024-08-06 API with Structured Outputs on Azure | Microsoft Community Hub"


### Azure embeddings shortened to 768 dims
*How to call text-embedding-3-large (or current) with dimensions=768 and confirm HNSW<=2000 and Vector(768) parity?*

Azure OpenAI's embeddings API (now unified under the `/openai/v1/embeddings` endpoint, confirmed current as of 2026-07-22/2026-07-09) accepts a `dimensions` integer request field (min: 1, no stated max in the REST schema) that is supported for `text-embedding-3-large`, `text-embedding-3-small`, and later models; passing `dimensions=768` returns a 768-float vector directly from the API via Matryoshka-style truncation, so the app never has to truncate/renormalize client-side. pgvector's `vector` column type supports up to 16,000 dimensions for storage, but its HNSW (and IVFFlat) index caps out at 2,000 dimensions for the plain `vector` type -- 768 is well inside that cap, so `Vector(768)` with an HNSW index is valid with no index-type change needed. Parity is confirmed by asserting `len(response.data[0].embedding) == 768` on the API response and checking it matches the SQLAlchemy column's `Vector(768)` dimension used by the existing pgvector/pg_trgm schema. Older date-versioned (classic, non-v1) Azure OpenAI api-version strings almost certainly also support `dimensions` since it shipped alongside the text-embedding-3 model family, but I could not open a classic-version-pinned reference page confirming the exact earliest date-based api-version string that supports it, so that specific compatibility claim is [uncertain].

**Key findings**
- Azure OpenAI v1 Create Embedding REST reference (learn.microsoft.com, doc dated 2026-05-27/updated 2026-07-09) lists request field `dimensions: integer, min:1, No` -- 'The number of dimensions the resulting output embeddings should have. Only supported in text-embedding-3 and later models.'
- Azure 'Generate embeddings' how-to (learn.microsoft.com, updated 2026-07-22) documents the current recommended call path as `{endpoint}/openai/v1/embeddings` using Microsoft Entra ID (DefaultAzureCredential) or API-key auth; SDK call is `openai.embeddings.create(model=..., input=...)` and a `dimensions=768` kwarg can be added to the same call.
- pgvector README (github.com/pgvector/pgvector, fetched directly) states HNSW/IVFFlat index support: 'vector - up to 2,000 dimensions; halfvec - up to 4,000 dimensions; bit - up to 64,000 dimensions; sparsevec - up to 1,000 non-zero elements', and separately 'Vectors can have up to 16,000 dimensions' for the base `vector` type.
- 768 < 2,000, so a plain `vector(768)` column with a standard HNSW index (no `halfvec` cast needed) is within pgvector's supported range -- no schema/index-type change required versus the existing Vector(768) definition.
- text-embedding-3-large has a default output of 3072 dimensions and a documented supported `dimensions` range of 1-3072 per multiple vendor/secondary pages (Zilliz model card, Azure AI Search truncate-dimensions doc); Azure's own truncate-dimensions doc (learn.microsoft.com, ms.date 2026-01-31) notes it allows truncation 'as low as 256' for -large under its Azure AI Search-specific MRL/quantization feature.
- The Azure AI Search 'Truncate Dimensions' MRL feature (learn.microsoft.com) is a different mechanism from the raw embeddings API `dimensions` param: it operates at the Azure AI Search vector-index level (`truncationDimension` + scalar/binary quantization) and is NOT what this build needs, since the build stores vectors directly in Postgres/pgvector, not Azure AI Search.
- Microsoft's own Azure SQL dev blog (devblogs.microsoft.com, article) recommends 1024 dims as a 'sweet spot' for text-embedding-3-large (4KB vs 12KB storage) and cites MTEB benchmark data showing usable quality even at 256 dims for -large, supporting that 768 is a safe, quality-preserving reduction.
- Embedding request limits per the same official REST reference: max 8,192 input tokens per item, max 2,048 items per array input, and a 300,000-token aggregate cap per request across all inputs.

**Recommendations**
- Call the embeddings endpoint with `model=<deployment-name>` and `dimensions=768` in the request body (SDK: `client.embeddings.create(model=..., input=..., dimensions=768)`); verify output length is exactly 768 in a unit test before any DB write.
- Keep the Postgres column as `Vector(768)` with a standard HNSW index unchanged -- no `halfvec` migration is needed since 768 is far under pgvector's 2,000-dim HNSW cap.
- Do NOT use the Azure AI Search 'truncationDimension' / MRL quantization feature for this build -- that's an Azure AI Search index-level concept, unrelated to the direct-to-Postgres pgvector path this build uses.
- Add a parity test asserting `len(embedding) == 768` and, ideally, a cosine-similarity sanity check between an Azure-produced 768-dim vector and a fixed reference query vs. the prior GCP/Vertex embedding ranking, to satisfy the before/after top-k comparison acceptance criterion.
- Prefer the current `/openai/v1/embeddings` endpoint/SDK surface (Entra ID or API key) shown in the 2026-07-22 how-to doc over a hardcoded legacy date-based api-version, since Microsoft documents v1 as the forward path; if a classic date-versioned api-version is already pinned elsewhere in the codebase, explicitly re-verify the `dimensions` field is accepted on that pinned version before relying on it in production.

*As of: 2026-07-22 (Azure 'Generate embeddings' how-to) / 2026-07-09 (Azure OpenAI v1 Embeddings REST reference) / 2026-01-31 (Azure AI Search truncate-dimensions doc); pgvector README fetched live, version not dated on page*

**Sources**
- [Microsoft Foundry REST Reference - Azure OpenAI - Embeddings](https://learn.microsoft.com/en-us/rest/api/microsoft-foundry/azureopenai/embeddings) (official-docs) -- "dimensions | integer | The number of dimensions the resulting output embeddings should have. Only supported in text-embedding-3 and later models. Constraints: min: 1"
- [Generate embeddings with Azure OpenAI - Microsoft Foundry](https://learn.microsoft.com/en-us/azure/ai-foundry/openai/how-to/embeddings) (official-docs) -- "response = openai.embeddings.create(model="text-embedding-3-small", input="The quick brown fox jumped over the lazy dog.") ... Embedding dimensions: <number>"
- [pgvector GitHub repository](https://github.com/pgvector/pgvector) (repo) -- "Supported types are: vector - up to 2,000 dimensions; halfvec - up to 4,000 dimensions; bit - up to 64,000 dimensions; sparsevec - up to 1,000 non-zero elements ... Vectors can have up to 16,000 dimensions."
- [Truncate Dimensions - Azure AI Search](https://learn.microsoft.com/en-us/azure/search/vector-search-how-to-truncate-dimensions) (official-docs) -- "On Azure OpenAI, text-embedding-3 models are retrained on the Matryoshka Representation Learning (MRL) technique... If you're using the text-embedding-3-large model, you can set it as low as 256."
- [Embedding models and dimensions: optimizing the performance to resource-usage ratio - Azure SQL Dev Corner](https://devblogs.microsoft.com/azure-sql/embedding-models-and-dimensions-optimizing-the-performance-resource-usage-ratio/) (article) -- "developers can shorten embeddings... by passing in the dimensions API parameter... 1024 dimensions... uses 4KB of storage (versus 12KB for the full 3072 dimensions) while delivering pretty much the same performance."


### Azure AI Document Intelligence vs LLM vision OCR
*Accuracy/cost/API for scanned exam papers; how to A/B gate against Gemini OCR output on a sample?*

Azure AI Document Intelligence's Read model (prebuilt-read, API version 2024-11-30, part of v4.0 GA) is a mature, officially documented OCR service that returns per-word confidence scores and a handwriting-style flag per line, making it directly usable as an OCR-quality signal for an A/B gate. It accepts PDFs/images up to 500MB and 2000 pages (S0 tier) and extracts print and handwritten text from scanned exam papers. No rigorous, independent, task-specific benchmark comparing Azure Document Intelligence to Gemini vision OCR on handwritten exam content exists publicly; third-party comparison blogs report Azure as strong on printed text but weaker than LLM-vision OCR on messy/cursive handwriting, but these figures are vendor-adjacent or SEO-style summaries, not peer-reviewed. The build should therefore implement its own A/B gate (acceptance criterion 8) rather than relying on published numbers: run both engines on a real sample of scanned papers, score against a small human-corrected ground truth with CER/WER, and record pass/fail per sample.

**Key findings**
- Read model (prebuilt-read) is GA under API version 2024-11-30 as part of Document Intelligence v4.0; supports PDF, JPEG/PNG/BMP/TIFF/HEIF images, plus DOCX/XLSX/PPTX/HTML (Microsoft Learn, page dated 2026-08-15, last updated 2026-10-19).
- Paid (S0) tier: file size limit 500MB, up to 2000 pages per PDF/TIFF; free (F0) tier: 4MB file size, only first 2 pages processed, ~500 free pages/month.
- Analyze output includes per-word `confidence` scores and a top-level `styles` collection flagging `isHandwritten: true` per text line with its own confidence score -- usable directly as a quality signal in the A/B gate.
- Searchable-PDF output (`analyze?output=pdf`) is bundled free with prebuilt-read under API version 2024-11-30, no extra cost.
- Minimum extractable text height is 12px in a 1024x768 image (~8pt type at 150 DPI); image dimensions must be between 50x50px and 10,000x10,000px -- relevant for low-resolution WhatsApp photo scans of exam papers.
- [uncertain] Pay-as-you-go pricing is commonly cited by third-party pricing trackers at ~$1.50 per 1,000 pages for Read, dropping to ~$0.60/1,000 pages above 1M pages/month, with ~500 free pages/month on F0; the official Azure pricing page did not render live dollar figures when fetched directly, so these numbers are secondary-source, not confirmed from Azure's own calculator output.
- [uncertain] Third-party comparison articles (dated Jan 2026) report Azure Document Intelligence as the printed-text accuracy leader but weaker than GPT-5/Mistral-class vision OCR on pure/cursive handwriting (one source cites Azure ~78.2% vs Mistral OCR 3 ~88.9% on handwriting); the same article notes competing vendors' benchmarks are self-reported internal tests with no independent, identical-test-set comparison available, and no source found benchmarks Azure against Gemini specifically.
- No candidate academic paper benchmarks Azure Document Intelligence directly; 'Lost in OCR Translation' (arXiv:2505.05666) is relevant background showing that OCR errors on degraded/complex scanned documents can meaningfully hurt downstream retrieval quality even when raw text accuracy looks acceptable, supporting a retrieval-level (not just text-level) comparison in the gate.

**Recommendations**
- Implement Document Intelligence as the OCR adapter behind the existing OCR port using the `prebuilt-read` model, API version 2024-11-30 (Python SDK package `azure-ai-documentintelligence`), capturing per-line text, confidence, and isHandwritten flags.
- Build the OCR A/B gate (acceptance criterion 8) as a standalone script: run a fixed sample of real scanned exam papers through both Azure Read and the current Gemini OCR path, diff extracted text against a small human-corrected ground truth, score with CER/WER, and record a documented pass/fail per sample.
- Also compare downstream retrieval results (not just raw OCR text accuracy) on the same sample, since OCR errors can silently degrade retrieval even when word-level accuracy looks fine -- this mirrors the risk documented in 'Lost in OCR Translation' (arXiv:2505.05666).
- Reject or re-scan images below the ~12px/8pt-at-150-DPI text-height threshold or under 50x50px before sending to OCR, since sub-threshold scans won't extract reliably in either engine.
- Do not hardcode per-page OCR cost into the daily cost-cap breaker from aggregator-sourced pricing; pull the live rate from the Azure Pricing Calculator or billing APIs for the actual resource region/tier before wiring it into the cost-cap test.
- Treat handwriting-heavy exam answer scans as the highest-risk bucket in the A/B gate's sample set, given consistent (though unverified) third-party reports that OCR engines degrade most on cursive/messy handwriting versus clean print.

*As of: 2026-11-02; Document Intelligence Read docs last updated 2026-10-19 (v4.0 GA, API version 2024-11-30); third-party pricing/accuracy figures checked/dated Jan-Oct 2026*

**Sources**
- [Read model OCR data extraction - Document Intelligence - Foundry Tools | Microsoft Learn](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/prebuilt/read?view=doc-intel-4.0.0) (official-docs) -- "Document Intelligence Read Optical Character Recognition (OCR) model runs at a higher resolution than Azure Vision Read and extracts print and handwritten text from PDF documents and scanned images."
- [Azure AI Document Intelligence Pricing](https://azure.microsoft.com/en-us/pricing/details/ai-document-intelligence/) (official-docs) -- "0 - 500 pages free per month"
- [Azure Document Intelligence pricing per 1,000 pages](https://plosys.com/blog/48234-azure-document-intelligence-pricing-what-drives-the-cost/) (article) -- "$1.50 per 1,000 pages for the Read model, which drops to $0.60 per 1,000 pages after the first million pages in a month"
- [Azure OCR Comparison: Mistral, GPT & Document Intelligence](https://jannikreinhard.com/master-the-paper-chaos-comparing-azures-ocr-and-document-intelligence-powerhouses/) (article) -- "Mistral's benchmarks are 'internal'—conducted by the vendor themselves. Independent comparisons using identical test sets are still lacking."
- [Lost in OCR Translation? Vision-Based Approaches to Robust Document Retrieval](https://arxiv.org/abs/2505.05666) (paper) -- "Traditional RAG systems rely on Optical Character Recognition (OCR) to first process scanned documents into text. However, even state-of-the-art OCRs can introduce errors, especially in degraded or complex documents."


### Azure Postgres Flexible Server pgvector+pg_trgm
*Enabling pgvector/pg_trgm, HNSW support, connection via managed identity, and backup/restore drill mechanics?*

Azure Database for PostgreSQL Flexible Server supports pgvector (vector extension) and pg_trgm, but both must first be added to the server-level `azure.extensions` allow-list parameter before `CREATE EXTENSION` will succeed. HNSW indexing is supported with dimension limit of 2000 (fine for 768-dim embeddings) and tunable `m`/`ef_construction`/`ef_search` params; DiskANN is Azure's recommended alternative if HNSW hits CPU-instruction compatibility issues on some hardware with pgvector 0.8.0. Managed-identity/Entra ID auth works by acquiring an OAuth token scoped to `https://ossrdbms-aad.database.windows.net/.default` (token valid 5-60 min, must be refreshed, used as the Postgres password) rather than a static password. Backup/restore drills use built-in point-in-time restore (default 7-day retention, up to 35 days) or geo-restore (if geo-redundant backup enabled at creation, ~1hr RPO, no PITR on the geo copy); a restore always creates a new server, never overwrites in place, so the drill procedure is: trigger a PITR/geo-restore to a new server name, verify data/extensions, then tear it down.

**Key findings**
- pgvector extension is named `vector` on Azure (not `pgvector`); enabling requires: 1) add `vector` and `pg_trgm` to server parameter `azure.extensions` (Portal > Server parameters, or `az postgres flexible-server parameter set --name azure.extensions --value vector,pg_trgm`), then 2) run `CREATE EXTENSION vector;` / `CREATE EXTENSION pg_trgm;` in the DB.
- Index column dimension limit is 2000 for both ivfflat and hnsw; attempting to index >2000 dims throws 'column cannot have more than 2000 dimensions for INDEX_TYPE index'. 768 dims is well within this limit.
- HNSW CREATE INDEX syntax: `CREATE INDEX ... USING hnsw (embedding vector_l2_ops) WITH (m = 16, ef_construction = 64);` defaults m=16, ef_construction=64, ef_search=40 (settable via `SET hnsw.ef_search`).
- Microsoft Q&A/docs report pgvector 0.8.0 can hit an 'illegal instruction' crash on Flexible Server due to CPU-instruction mismatches; Microsoft's documented mitigation is to use DiskANN (Azure-specific index type, only available on Flexible Server) instead of HNSW if this is encountered. [uncertain]
- Entra ID / managed-identity auth: get a token via `az account get-access-token --resource-type oss-rdbms` (or equivalent SDK call scoped to `https://ossrdbms-aad.database.windows.net/.default`), then pass it as the PostgreSQL password (e.g. `PGPASSWORD` env var); token is valid only 5-60 minutes and must be re-acquired, so app code needs refresh logic rather than a cached static credential.
- Both system-assigned and user-assigned managed identities are supported as Entra principals/admins on Flexible Server; a managed identity can also be a member of an Entra group role for scoped DB permissions.
- Default backup retention is 7 days, configurable up to 35 days; first backup is a full snapshot, subsequent ones are daily differential snapshots, WAL backed up continuously (RPO up to ~5 min).
- Restore always provisions a brand-new server (never in-place); options are latest restore point, custom (any point within retention window), fast-restore (snapshot only, no WAL replay), and geo-restore (to paired region, only if geo-redundant backup was enabled at server creation time, ~1hr RPO, no PITR on the geo copy).
- Geo-redundant backup storage can only be enabled at server creation time and cannot be toggled on afterward; must wait at least 1 hour post-creation before the first geo-restore is possible.
- Post-restore, firewall rules, VNet/private-endpoint config, server parameters (including `azure.extensions`), and HA config are NOT automatically copied to the restored server and must be reapplied manually — relevant for scripting a restore drill.

**Recommendations**
- Add both `vector` and `pg_trgm` to the `azure.extensions` allow-list in the Bicep template's server parameters resource (not just via post-deploy SQL), so `CREATE EXTENSION` doesn't fail on a fresh subscription.
- Keep `Vector(768)` column type and HNSW index DDL as-is (`vector_cosine_ops` or current distance op); 768 dims is within Azure's 2000-dim index limit, so no column/index redesign is needed.
- Build the Postgres connection string/engine to support Entra managed-identity auth with token refresh (acquire token scoped to `https://ossrdbms-aad.database.windows.net/.default`, refresh before each connection or on expiry) as the secrets adapter's default for Azure, falling back to password auth only for local/dev.
- If HNSW build/query throws an illegal-instruction error on the chosen Flexible Server SKU, fall back to DiskANN as Azure's documented stable alternative rather than debugging CPU-flag issues — flag this as a contingency in the migration runbook, not a default assumption.
- For the required restore drill: set backup retention explicitly in Bicep (7-35 days) and geo-redundant backup only if enabling at creation; script the drill as PITR-to-new-server-name, verify pgvector extension + HNSW index + row counts exist, then delete the drill server — document that firewall/VNet/parameters must be reapplied post-restore.
- Do not assume PITR works on a geo-redundant backup copy — only geo-restore (to the paired region, latest backup only) is available there; keep this distinction explicit in the RUNBOOK's DR section.

*As of: Docs pages dated/updated 2026-07 to 2026-09 (Microsoft Learn ms.date fields); pgvector 0.8.0 release referenced as May 2025*

**Sources**
- [Optimize Performance when Using pgvector in Azure Database for PostgreSQL Flexible Server](https://learn.microsoft.com/en-us/azure/postgresql/extensions/how-to-optimize-performance-pgvector) (official-docs) -- "You can only index a column that has up to 2000 dimensions... ERROR: column cannot have more than 2000 dimensions for INDEX_TYPE index"
- [Use Microsoft Entra ID Authentication in Azure Database for PostgreSQL Flexible Server](https://learn.microsoft.com/en-us/azure/postgresql/security/security-entra-configure) (official-docs) -- "az account get-access-token --resource-type oss-rdbms ... The access token is valid for 5 to 60 minutes. Get the access token before initiating the sign-in to Azure Database for PostgreSQL."
- [Backup and Restore in Azure Database for PostgreSQL Flexible Server](https://learn.microsoft.com/en-us/azure/postgresql/backup-restore/concepts-backup-restore) (official-docs) -- "A restore operation in your Azure Database for PostgreSQL flexible server instance always creates a new database server with the name that you provide. It doesn't overwrite the existing database server."
- [pg_trgm Extension Not Allowed on Azure Database for PostgreSQL Flexible Server (search summary of Microsoft docs/Q&A)](https://learn.microsoft.com/en-us/answers/questions/5537068/pg-trgm-extension-not-allowed-on-azure-database-fo) (forum) -- "azure.extensions is the server parameter that holds Azure's per-server allow-list of extensions."
- [Azure Database for PostgreSQL flexible server - Illegal instruction with pgvector 0.8.0](https://learn.microsoft.com/en-us/answers/questions/5544878/azure-database-for-postgresql-flexible-server-ille) (forum) -- "The vector extension (version 0.8.0) may use CPU instructions that aren't supported on specific hardware behind the PostgreSQL Flexible Server. DiskANN is recommended as a stable alternative to HNSW."
- [Tutorial: Access Azure databases with managed identity - Azure App Service](https://learn.microsoft.com/en-us/azure/app-service/tutorial-connect-msi-azure-database) (official-docs) -- "Secure database connectivity (Azure SQL Database, Database for MySQL, and Database for PostgreSQL) with managed identity from .NET, Node.js, Python, and Java apps."


### Container Apps + Jobs + ACR via Bicep
*Parameterized Bicep for web apps and jobs, ingress on 8080, managed identity, ACR pull; replacing Cloud Run scripts?*

Yes: parameterized Bicep can replace Cloud Run deploy scripts using Microsoft.App/containerApps for the web/bot service (ingress targetPort 8080) and Microsoft.App/jobs for batch/import work (e.g. the Graph import), both authenticating to ACR via managed identity so no registry passwords are stored. Microsoft's official pattern uses a user-assigned managed identity granted the built-in AcrPull role, referenced in the containerApp/job's `identity` block and in `configuration.registries[].identity`; system-assigned identity also works but Microsoft recommends user-assigned to avoid circular create-then-assign dependencies. Jobs support Manual, Schedule, and Event trigger types (cron for Schedule, KEDA-based scalers for Event) and are the direct Azure analogue of Cloud Run Jobs, sharing the same Container Apps environment as the web app for networking/logging.

**Key findings**
- Official Microsoft Learn Bicep example (updated 2025-10-08) sets `ingress: { targetPort: 8080, external: true }` on `Microsoft.App/containerApps@2022-06-01-preview` and configures `registries: [{ server: '<acr>.azurecr.io', identity: identity.id }]` with no secrets.
- ACR must allow ARM-audience tokens for managed-identity pulls: `az acr config authentication-as-arm show/update -r <REGISTRY> --status enabled`.
- The built-in AcrPull role definition ID is 7f951dda-4ed3-4680-a7ca-43fe172d538d; Microsoft's sample grants it to the identity via a `Microsoft.Authorization/roleAssignments` resource using `guid(resourceGroup().id, acr, 'AcrPullTestUserAssigned')`.
- Microsoft explicitly recommends: 'When possible, you should use a user-assigned managed identity to pull images' (over system-assigned) for ACR pull scenarios.
- Current Microsoft.App/containerApps template schema (fetched, API version 2026-07-01) confirms ingress supports external/targetPort/transport ('auto'|'http'|'http2'|'tcp'), and `identity.type` accepts 'SystemAssigned', 'UserAssigned', or both combined.
- Container Apps Jobs (Microsoft.App/jobs) is the Cloud Run Jobs equivalent: official docs (page dated 2026-09-16) describe triggerType 'Manual' | 'Schedule' | 'Event', with scheduleTriggerConfig.cronExpression, manualTriggerConfig.parallelism/replicaCompletionCount, and eventTriggerConfig.scale (KEDA scale rules, e.g. azure-queue).
- Jobs share registries/identity config identical to containerApps (same `registries[].identity` + managed-identity block), confirmed on the same docs page's ARM JSON example using `registry-server`/`registry-username`/`registry-password` or identity-based auth.
- Jobs restrictions per official docs: Dapr and ingress (and related custom domains/SSL) are NOT supported on jobs -- jobs are compute-only, batch-style workloads.
- The Azure Verified Module (AVM) 'avm/res/app/job' (Azure/bicep-registry-modules repo) wraps this with a `managedIdentities` object (`systemAssigned`/`userAssignedResourceIds`) and the same `registries[].identity` + `triggerType`/`scheduleTriggerConfig` shape, giving a maintained, parameterized starting point instead of hand-rolling the resource.
- `az containerapp job start`, `az containerapp job execution list`, and the REST `jobs/{name}/start` (api-version 2023-05-01) operation are the mechanisms to invoke/monitor a job programmatically -- useful for the Graph-import job's operational runbook.

**Recommendations**
- Use one Bicep module for the web/bot Container App (ingress targetPort 8080, external true) and a separate Microsoft.App/jobs module for the Graph import (triggerType Schedule or Manual), both under the same Container Apps environment so logging/networking are shared.
- Create one user-assigned managed identity per workload (or a shared one if acceptable) and grant it AcrPull (role ID 7f951dda-4ed3-4680-a7ca-43fe172d538d) on the ACR; reference it via `registries[].identity` on both the app and the job rather than embedding registry admin credentials.
- Enable ARM-audience tokens on the ACR (`az acr config authentication-as-arm update --status enabled`) as a prerequisite step in the deployment docs/runbook, since managed-identity pulls fail silently otherwise.
- Parameterize image tag, CPU/memory, cron expression (for the import job), and ACR/registry name so the same Bicep can target dev/staging/prod without edits, matching the 'parameterized Bicep' requirement.
- Do not add ingress or Dapr to the Graph-import job -- official docs confirm jobs don't support ingress, so any HTTP-triggerable import logic must live in the web app or be invoked via the Jobs Start REST/CLI API instead.
- Consider adopting the AVM `avm/res/app/job` and an equivalent `avm/res/app/container-app` module instead of hand-written resources, since they already encode the identity/ACR-pull pattern and reduce custom Bicep surface area to maintain.
- For the daily cost-cap breaker (acceptance criterion 10), note Jobs restrictions and the separate Job vs App billing model when wiring cost checks -- scheduled job executions bill per execution duration, distinct from the always-on app.

*As of: Pages fetched 2026-11-02; Microsoft Learn 'jobs' doc last updated 2026-09-16, 'managed-identity-image-pull' doc last updated 2025-10-08, containerApps template reference reflects API version 2026-07-01 (latest at fetch time).*

**Sources**
- [Azure Container Apps image pull from Azure Container Registry with managed identity](https://learn.microsoft.com/en-us/azure/container-apps/managed-identity-image-pull) (official-docs) -- "Your Azure Container Registry must allow ARM audience tokens for authentication in order to use managed identity to pull images... When possible, you should use a user-assigned managed identity to pull images."
- [Microsoft.App/containerApps - Bicep, ARM template & Terraform AzAPI reference](https://learn.microsoft.com/en-us/azure/templates/microsoft.app/containerapps) (official-docs) -- "identity: { type: 'string' } // Required: 'None', 'SystemAssigned', 'UserAssigned', 'SystemAssigned,UserAssigned' ... registries: [ { identity: 'string', server: 'string' } ]"
- [Jobs in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/jobs?tabs=azure-cli) (official-docs) -- "A job's trigger type determines how the job is started... Manual, Schedule, Event... The following features aren't supported: Dapr; Ingress and related features such as custom domains and SSL certificates."
- [Microsoft.App/jobs - Bicep, ARM template & Terraform AzAPI reference](https://learn.microsoft.com/en-us/azure/templates/microsoft.app/jobs) (official-docs) -- "ms.date: 2024-12-09 ... Microsoft.App/jobs syntax and properties to use in Azure Resource Manager templates for deploying the resource."
- [GitHub - Azure-Samples/container-apps-jobs](https://github.com/Azure-Samples/container-apps-jobs) (repo) -- "This sample shows how to create Azure Container Apps Jobs via Azure CLI and Bicep and how to start and monitor these components."
- [bicep-registry-modules avm/res/app/job README](https://github.com/Azure/bicep-registry-modules/blob/main/avm/res/app/job/README.md) (repo) -- "managedIdentities: { systemAssigned: true, userAssignedResourceIds: [...] } ... registries: [{ server: 'myregistry.azurecr.io', identity: '<identity>' }] ... triggerType: 'Schedule'"
- [Azure built-in roles - AcrPull](https://learn.microsoft.com/en-us/azure/role-based-access-control/built-in-roles#acrpull) (official-docs) -- "Role ID (GUID): 7f951dda-4ed3-4680-a7ca-43fe172d538d; Description: Pull artifacts from a container registry."


### Key Vault + managed identity config loader
*How to load secrets via Key Vault references/managed identity in Container Apps to replace GCP Secret Manager pattern?*

Azure Container Apps has native Key Vault reference secrets: a secret is defined with a keyVaultUrl plus an identity (system- or user-assigned managed identity), and Container Apps auto-resolves/refreshes the value, replacing the GCP Secret Manager + service-account pattern. On the app side, pydantic-settings ships a built-in AzureKeyVaultSettingsSource that uses azure-identity's DefaultAzureCredential (which resolves to the Container App's managed identity in Azure and to az login locally) to pull secrets inside settings_customise_sources. Combine both: platform-level keyvaultref secrets for simple env-var values (rotation handled by the platform), and AzureKeyVaultSettingsSource in the config loader for structured/bulk secret loading, mirrored as the Azure branch of the existing secrets abstraction.

**Key findings**
- Container Apps Key Vault reference CLI syntax: --secrets 'name=keyvaultref:<KEY_VAULT_SECRET_URI>,identityref:<IDENTITY_ID>'; ARM template uses secrets[].keyVaultUrl + identity:'system' or a user-assigned identity resource ID (learn.microsoft.com/azure/container-apps/manage-secrets, page dated 2026-09-04, updated 2026-09-11).
- Managed identity must be enabled before referencing Key Vault secrets; the identity needs RBAC role 'Key Vault Secrets User' on the vault (RBAC model, not legacy access policies), per same doc.
- If the Key Vault URI omits a version, Container Apps auto-polls and picks up the latest secret version within 30 minutes, restarting active revisions that reference it in an env var; the platform handles rotation.
- System-assigned identity can't be used with `az containerapp create` because it doesn't exist yet; only a user-assigned identity works at create time per the CLI docs.
- PowerShell (New-AzContainerApp / New-AzContainerAppSecretObject) does NOT support Key Vault secret references; only ARM template or Azure CLI paths support keyVaultUrl, per the same doc.
- pydantic-settings provides AzureKeyVaultSettingsSource, installed via the extra `pydantic-settings[azure-key-vault]` (pulls in azure-identity and azure-keyvault-secrets); current PyPI release is 2.16.2, dated 2026-10-28.
- AzureKeyVaultSettingsSource(settings_cls, vault_url, credential) is wired in by overriding settings_customise_sources() and returning it in the source tuple, used with DefaultAzureCredential(); docs state DefaultAzureCredential resolves via `az login` for local dev.
- AzureKeyVaultSettingsSource also supports dash_to_underscore and nested-model key naming via a '--' separator, per the pydantic.dev settings management page.

**Recommendations**
- Implement a KeyVaultSettingsSource adapter wrapping pydantic-settings' AzureKeyVaultSettingsSource + DefaultAzureCredential as the Azure branch of the existing secrets/config abstraction, parallel to the GCP Secret Manager adapter.
- Assign a user-assigned managed identity (not system-assigned) to the Container App and jobs so the identity resource ID can be referenced in Bicep before the app itself is created, and shared across the API app and Container Apps Jobs.
- Grant 'Key Vault Secrets User' scoped to the Key Vault resource only (not resource group/subscription), for least-privilege parity with GCP's per-secret IAM bindings.
- For simple scalar secrets (DB password, API keys) used as env vars, prefer platform-level keyvaultref secrets over in-app fetches, since Azure handles the ~30 min rotation/restart automatically.
- Keep AzureKeyVaultSettingsSource only in the Azure settings_customise_sources path; retain the local/dotenv source for local dev and tests so they don't require live Azure credentials.
- Default to unversioned Key Vault secret URIs (no pinned version) so automatic rotation works; only pin a version if you explicitly need to freeze a secret.
- Use the Bicep/ARM path (which natively supports keyVaultUrl + identity) for all secret provisioning rather than PowerShell cmdlets, consistent with the acceptance criterion requiring `az deployment` with Bicep templates.

*As of: 2026-11-02; Container Apps manage-secrets doc last updated 2026-09-11 (ms.date 2026-09-04); pydantic-settings 2.16.2 released 2026-10-28 per PyPI*

**Sources**
- [Manage secrets in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/manage-secrets) (official-docs) -- "To specify a Key Vault reference, use the format <SECRET_NAME>=keyvaultref:<KEY_VAULT_SECRET_URI>,identityref:<MANAGED_IDENTITY_ID>... grant the Azure RBAC role Key Vault Secrets User to the managed identity."
- [Settings Management - Pydantic documentation](https://pydantic.dev/docs/validation/latest/concepts/pydantic_settings/) (official-docs) -- "az_key_vault_settings = AzureKeyVaultSettingsSource(settings_cls, os.environ['AZURE_KEY_VAULT_URL'], DefaultAzureCredential())"
- [pydantic-settings · PyPI](https://pypi.org/project/pydantic-settings/) (official-docs) -- "Version: 2.16.2, Release Date: October 28, 2026 ... azure-key-vault extra is available among the optional extras."


### Microsoft Graph SharePoint/OneDrive import
*Graph API for listing/downloading drive files with auth and keeping sha256 dedupe, replacing Drive import?*

Microsoft Graph's driveItem API supports listing (children/delta endpoints) and downloading (content endpoint or @microsoft.graph.downloadUrl) files from OneDrive/SharePoint drives, and can fully replace the Google Drive import. Auth should use azure-identity's ClientSecretCredential (app-only client credentials flow) with the Files.Read.All or Sites.Read.All application permission, reusing the same azure-identity dependency likely already needed for Key Vault secrets. The critical gap: Graph's hashes facet explicitly does NOT support sha256Hash ('isn't supported, don't use') -- only quickXorHash (guaranteed) and sha1Hash (if available) are returned, so sha256 dedupe must be computed locally by hashing the downloaded bytes, not read from Graph metadata. Delta query (driveItem: delta) is the recommended replacement for Drive's changes.list to do incremental sync efficiently.

**Key findings**
- GET /drives/{drive-id}/items/{item-id}/children lists folder contents; paginates via @odata.nextLink with a default page size of 200 items (learn.microsoft.com, updated 2025-11-25).
- GET /drives/{drive-id}/items/{item-id}/content (or /root:/{path}:/content) returns HTTP 302 redirecting to a preauthenticated download URL; this is identical to the @microsoft.graph.downloadUrl property; URLs can expire within minutes and need no Authorization header (learn.microsoft.com, doc dated 2024-06-12, page updated 2025-08-27).
- Range header (RFC 2616) is supported for partial/chunked downloads against the downloadUrl, returning 206 Partial Content -- useful for large PDFs.
- The hashes resource (v1.0) explicitly states sha256Hash 'isn't supported. Don't use.' Only quickXorHash is guaranteed across OneDrive personal and business/SharePoint; sha1Hash is available 'if available' (learn.microsoft.com/graph/api/resources/hashes, updated 2025-04-09).
- driveItem: delta function (GET /drives/{drive-id}/root/delta) is the Graph equivalent of a change feed: first call returns items plus either @odata.nextLink (more pages) or @odata.deltaLink (save for next sync); subsequent calls against the saved deltaLink return only changed/deleted items (learn.microsoft.com/graph/delta-query-overview, updated 2025-01-15, page last touched 2026-05-14).
- Least-privileged application permission for both listing and downloading is Files.Read.All (OneDrive) or Sites.Read.All (SharePoint site drives); these require admin consent in Entra ID and work via client-credentials flow (learn.microsoft.com/graph/api/driveitem-get-content and driveitem-list-children, both v1.0, same permissions table).
- Official Python app-only tutorial (updated 2025-06-03) uses `azure-identity` (ClientSecretCredential) for the token plus the `msgraph-sdk` (Python, preview) package, scope `https://graph.microsoft.com/.default`, not a raw MSAL call -- matching an Azure-adapter style already needed for Key Vault.
- Deleted items in a delta response appear as `{id, "@removed": {"reason": "deleted"|"changed"}}`, so the import job can detect removals without a full re-scan.
- Delta tokens for driveItem are not listed under the fixed 7-day expiry group (that applies to directory/education objects); OneDrive/SharePoint delta links instead can return 410 Gone with an empty-token Location header when a full resync is forced by the service -- the importer must handle this by restarting from a full scan.

**Recommendations**
- Download file bytes via @microsoft.graph.downloadUrl (or follow the /content 302), then compute sha256 locally in the import adapter for dedupe -- do not attempt to read a sha256 hash from Graph metadata; it is unsupported.
- Optionally also store quickXorHash (always available) as a cheap 'did-content-change' pre-check before doing a full download+sha256, to cut bandwidth on re-scans.
- Use azure-identity ClientSecretCredential for app-only auth with Files.Read.All (OneDrive) or Sites.Read.All (SharePoint), matching the Key Vault adapter's existing Azure SDK auth pattern -- this keeps the credential surface consistent across adapters.
- Implement listing with driveItem: delta instead of a plain children walk so repeat imports are incremental; persist the @odata.deltaLink per source folder and handle 410 Gone by falling back to a full children walk.
- Treat download URLs as single-use/short-lived: fetch @microsoft.graph.downloadUrl immediately before use, don't cache it across retry loops, and use the Range header for chunked downloads of large scanned-paper PDFs/images.
- Keep the existing sha256-based dedupe table/index unchanged in the DB layer; only the upstream source of the hash changes (computed from Graph-downloaded bytes instead of Drive's provided hash, if Drive previously supplied one).

*As of: v1.0 Graph API docs as current 2025-08-27 (content endpoint) / 2025-11-25 (children endpoint) / 2025-04-09 (hashes resource) / 2025-01-15 (delta query overview, page touched 2026-05-14); Python app-only tutorial dated 2025-06-03.*

**Sources**
- [Download driveItem content - Microsoft Graph v1.0](https://learn.microsoft.com/en-us/graph/api/driveitem-get-content?view=graph-rest-1.0) (official-docs) -- "Returns a 302 Found response redirecting to a preauthenticated download URL for the file... Preauthenticated download URLs are valid for a limited time... might expire within minutes."
- [List the contents of a folder - Microsoft Graph v1.0](https://learn.microsoft.com/en-us/graph/api/driveitem-list-children?view=graph-rest-1.0) (official-docs) -- "If a collection exceeds the default page size (200 items), the @odata.nextLink property is returned in the response to indicate more items are available."
- [hashes resource type - Microsoft Graph v1.0](https://learn.microsoft.com/en-us/graph/api/resources/hashes) (official-docs) -- "sha256Hash | String | This property isn't supported. Don't use. ... quickXorHash is the only value that is guaranteed to be available for both OneDrive for work or school and OneDrive for home."
- [Use delta query to track changes in Microsoft Graph data](https://learn.microsoft.com/en-us/graph/delta-query-overview) (official-docs) -- "Delta query can return a response code of 410 Gone ... This status usually happens to prevent data inconsistency... and is an indication that the application must restart with a full synchronization."
- [Build Python apps with Microsoft Graph and app-only authentication](https://learn.microsoft.com/en-us/graph/tutorials/python-app-only) (official-docs) -- "Azure Identity client library for Python to authenticate the user and acquire access tokens. Microsoft Graph SDK for Python (preview) to make calls to the Microsoft Graph."

## Documentation sources

- [What's new in Azure OpenAI in Microsoft Foundry Models? (classic)](https://learn.microsoft.com/en-us/azure/ai-services/openai/whats-new)
- [Azure OpenAI image and audio REST API reference (2024-10-21) - Microsoft Foundry](https://learn.microsoft.com/en-us/azure/ai-services/openai/reference)
- [Azure OpenAI in Microsoft Foundry Models v1 API](https://learn.microsoft.com/en-us/azure/ai-services/openai/api-version-lifecycle)
- [Microsoft Foundry REST Reference - Azure OpenAI - Embeddings](https://learn.microsoft.com/en-us/rest/api/microsoft-foundry/azureopenai/embeddings)
- [How-to: Create and deploy an Azure OpenAI in Microsoft Foundry Models resource (classic)](https://learn.microsoft.com/en-us/azure/ai-services/openai/how-to/create-resource)
- [Microsoft Foundry docs: What's new for August 2026](https://learn.microsoft.com/en-us/azure/foundry/whats-new-foundry)
- [Microsoft Foundry portal general availability overview](https://learn.microsoft.com/en-us/azure/foundry/concepts/general-availability)
- [Azure OpenAI in Microsoft Foundry Models v1 API](https://learn.microsoft.com/en-us/azure/foundry/openai/api-version-lifecycle)
- [Quickstart: Document Intelligence client libraries - Foundry Tools](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/quickstarts/get-started-sdks-rest-api?view=doc-intel-4.0.0)
- [Generate embeddings with Azure OpenAI - Microsoft Foundry | Microsoft Learn](https://learn.microsoft.com/en-us/azure/ai-foundry/openai/how-to/embeddings)
- [Foundry Models lifecycle and support policy - Microsoft Foundry | Microsoft Learn](https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/model-retirements)
- [Azure OpenAI in Microsoft Foundry Models v1 API - Microsoft Learn](https://learn.microsoft.com/en-us/azure/ai-foundry/openai/api-version-lifecycle)
- [Vector embeddings - OpenAI API documentation](https://developers.openai.com/api/docs/guides/embeddings)
- [Read model OCR data extraction - Document Intelligence - Foundry Tools | Microsoft Learn](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/prebuilt/read?view=doc-intel-4.0.0)
- [Document Intelligence SDK target REST API v4.0 - Foundry Tools | Microsoft Learn](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/versioning/sdk-overview-v4-0?view=doc-intel-4.0.0)
- [Migrate to v4.0 - Foundry Tools | Microsoft Learn](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/versioning/migration-guide-overview)
- [Supported versions of PostgreSQL in Azure Database for PostgreSQL flexible server](https://learn.microsoft.com/en-us/azure/postgresql/configure-maintain/concepts-supported-versions)
- [Optimize Performance when Using pgvector in Azure Database for PostgreSQL Flexible Server](https://learn.microsoft.com/en-us/azure/postgresql/extensions/how-to-optimize-performance-pgvector)
- [Vector Search in Azure Database for PostgreSQL Flexible Server](https://learn.microsoft.com/en-us/azure/postgresql/extensions/how-to-use-pgvector)
- [Allow Extensions in Azure Database for PostgreSQL Flexible Server](https://learn.microsoft.com/en-us/azure/postgresql/extensions/how-to-allow-extensions)
- [Microsoft.DBforPostgreSQL/flexibleServers - Bicep, ARM template & Terraform AzAPI reference](https://learn.microsoft.com/en-us/azure/templates/microsoft.dbforpostgresql/flexibleservers)
- [pgvector GitHub repository (README)](https://github.com/pgvector/pgvector)
- [pgvector CHANGELOG](https://raw.githubusercontent.com/pgvector/pgvector/master/CHANGELOG.md)
- [List of Extensions and Modules by Name in Azure Database for PostgreSQL Flexible Server](https://learn.microsoft.com/en-us/azure/postgresql/extensions/concepts-extensions-versions)
- [Release Notes for Azure Database for PostgreSQL flexible server](https://learn.microsoft.com/en-us/azure/postgresql/release-notes/release-notes)
- [PostgreSQL: Documentation: current: F.35. pg_trgm](https://www.postgresql.org/docs/current/pgtrgm.html)
- [PostgreSQL: Release Notes 18.3](https://www.postgresql.org/docs/release/18.3/)
- [Azure Container Apps overview](https://learn.microsoft.com/en-us/azure/container-apps/overview)
- [Quickstart: Deploy an existing container image with the command line](https://learn.microsoft.com/en-us/azure/container-apps/get-started-existing-container-image)
- [Jobs in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/jobs)
- [Microsoft.App/jobs - Bicep, ARM template & Terraform AzAPI reference](https://learn.microsoft.com/en-us/azure/templates/microsoft.app/jobs)
- [API change log for Microsoft.App/jobs](https://learn.microsoft.com/en-us/azure/templates/microsoft.app/change-log/jobs)
- [Jobs - REST API (Azure Azure Container Apps) | Microsoft Learn](https://learn.microsoft.com/en-us/rest/api/resource-manager/containerapps/jobs?view=rest-resource-manager-containerapps-2025-07-01)
- [az containerapp job | Microsoft Learn](https://learn.microsoft.com/en-us/cli/azure/containerapp/job?view=azure-cli-latest)
- [Microsoft.App/jobs 2025-01-01 - Bicep, ARM template & Terraform AzAPI reference](https://learn.microsoft.com/en-us/azure/templates/microsoft.app/2025-01-01/jobs)
- [Introduction to Azure Container Registry](https://learn.microsoft.com/en-us/azure/container-registry/container-registry-intro)
- [Azure Container Registry FAQ](https://learn.microsoft.com/en-us/azure/container-registry/container-registry-faq)
- [Azure Container Registry SKU Features and Limits](https://learn.microsoft.com/en-us/azure/container-registry/container-registry-skus)
- [Microsoft.ContainerRegistry/registries 2025-04-01 - Bicep, ARM template & Terraform AzAPI reference](https://learn.microsoft.com/en-us/azure/templates/microsoft.containerregistry/2025-04-01/registries)
- [Microsoft.ContainerRegistry/registries 2025-06-01-preview - Bicep, ARM template & Terraform AzAPI reference](https://learn.microsoft.com/en-us/azure/templates/microsoft.containerregistry/2025-06-01-preview/registries)
- [What is Azure Key Vault? (Microsoft Learn)](https://learn.microsoft.com/en-us/azure/key-vault/general/basic-concepts)
- [Azure Key Vault developer's guide (Microsoft Learn)](https://learn.microsoft.com/en-us/azure/key-vault/general/developers-guide)
- [What's new for Azure Key Vault (Microsoft Learn)](https://learn.microsoft.com/en-us/azure/key-vault/general/whats-new)
- [Managed identities for Azure resources - overview](https://learn.microsoft.com/en-us/entra/identity/managed-identities-azure-resources/overview)
- [Managed identities in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/managed-identity)
- [Azure Identity client library for Python](https://learn.microsoft.com/en-us/python/api/overview/azure/identity-readme)
- [Use Microsoft Entra ID Authentication in Azure Database for PostgreSQL Flexible Server](https://learn.microsoft.com/en-us/azure/postgresql/security/security-entra-configure)
- [What is Microsoft Entra? - Microsoft Entra | Microsoft Learn](https://learn.microsoft.com/en-us/entra/fundamentals/whatis)
- [OAuth 2.0 client credentials flow on the Microsoft identity platform | Microsoft Learn](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-client-creds-grant-flow)
- [azure-identity · PyPI](https://pypi.org/project/azure-identity/)
- [Microsoft Entra Authentication in Azure Database for PostgreSQL Flexible Server | Microsoft Learn](https://learn.microsoft.com/en-us/azure/postgresql/security/security-entra-concepts)
- [Install Bicep tools - Azure Resource Manager | Microsoft Learn](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/install)
- [What is Bicep? - Azure Resource Manager | Microsoft Learn](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/overview)
- [Bicep CLI commands - Azure Resource Manager | Microsoft Learn](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/bicep-cli)
- [az deployment group | Microsoft Learn](https://learn.microsoft.com/en-us/cli/azure/deployment/group)
- [Microsoft.App/containerApps - Bicep, ARM template & Terraform AzAPI reference](https://learn.microsoft.com/en-us/azure/templates/microsoft.app/containerapps)
- [Microsoft.ContainerRegistry/registries - Bicep, ARM template & Terraform AzAPI reference](https://learn.microsoft.com/en-us/azure/templates/microsoft.containerregistry/registries)
- [Microsoft Graph overview - Microsoft Graph | Microsoft Learn](https://learn.microsoft.com/en-us/graph/overview)
- [Install a Microsoft Graph SDK - Microsoft Graph | Microsoft Learn](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation)
- [msgraph-sdk · PyPI](https://pypi.org/project/msgraph-sdk/)
- [Working with files in Microsoft Graph - Microsoft Graph v1.0 | Microsoft Learn](https://learn.microsoft.com/en-us/graph/api/resources/onedrive?view=graph-rest-1.0)
- [Authentication and authorization basics - Microsoft Graph | Microsoft Learn](https://learn.microsoft.com/en-us/graph/auth/auth-concepts)
- [Working with SharePoint sites in Microsoft Graph - Microsoft Graph v1.0 | Microsoft Learn](https://learn.microsoft.com/en-us/graph/api/resources/sharepoint?view=graph-rest-1.0)
- [SharePoint Add-Ins and Azure ACS retirement FAQ | Microsoft Learn](https://learn.microsoft.com/en-us/sharepoint/dev/sp-add-ins/add-ins-and-azure-acs-retirements-faq)
- [Overview of Selected Permissions in OneDrive and SharePoint - Microsoft Graph | Microsoft Learn](https://learn.microsoft.com/en-us/graph/permissions-selected-overview)
- [OneDrive for Developers - OneDrive dev center](https://learn.microsoft.com/en-us/onedrive/developer/?view=odsp-graph-online)
- [List the contents of a folder - Microsoft Graph v1.0](https://learn.microsoft.com/en-us/graph/api/driveitem-list-children?view=graph-rest-1.0)
- [Download driveItem content - Microsoft Graph v1.0](https://learn.microsoft.com/en-us/graph/api/driveitem-get-content?view=graph-rest-1.0)
- [Removal of Deprecated SharePoint & OneDrive Permission Resource Properties](https://devblogs.microsoft.com/microsoft365dev/removal-of-deprecated-sharepoint-onedrive-permission-resource-properties/)
- [Pre-authenticated (tempauth) URLs are retiring: move to Microsoft Entra ID tokens before April 1, 2027](https://devblogs.microsoft.com/microsoft365dev/pre-authenticated-tempauth-urls-are-retiring-move-to-microsoft-entra-id-tokens-before-april-1-2027/)
- [azure-storage-blob · PyPI](https://pypi.org/project/azure-storage-blob/)
- [Azure Storage Blobs client library for Python | Microsoft Learn](https://learn.microsoft.com/en-us/python/api/overview/azure/storage-blob-readme?view=azure-python)
- [azure-sdk-for-python CHANGELOG.md (azure-storage-blob)](https://github.com/Azure/azure-sdk-for-python/blob/main/sdk/storage/azure-storage-blob/CHANGELOG.md)
- [Azure Identity client library for Python | Microsoft Learn](https://learn.microsoft.com/en-us/python/api/overview/azure/identity-readme?view=azure-python)
- [azure-sdk-for-python CHANGELOG.md (azure-identity)](https://github.com/Azure/azure-sdk-for-python/blob/main/sdk/identity/azure-identity/CHANGELOG.md)
- [FastAPI - Release Notes](https://fastapi.tiangolo.com/release-notes/)
- [FastAPI (homepage) - requirements and installation](https://fastapi.tiangolo.com/)
- [fastapi on PyPI](https://pypi.org/project/fastapi/)
- [FastAPI - Events: startup and shutdown](https://fastapi.tiangolo.com/advanced/events/)
- [FastAPI - About FastAPI versions / Deployments - Concepts](https://fastapi.tiangolo.com/deployment/concepts/)
- [FastAPI CLI](https://fastapi.tiangolo.com/fastapi-cli/)
- [SQLAlchemy 2.0 Documentation (en/20/)](https://docs.sqlalchemy.org/en/20/)
- [SQLAlchemy 2.0 Changelog: What's New in SQLAlchemy 2.0?](https://docs.sqlalchemy.org/en/20/changelog/whatsnew_20.html)
- [SQLAlchemy asyncio extension docs](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
- [SQLAlchemy 2.0 Intro / Installation](https://docs.sqlalchemy.org/en/20/intro.html#installation)
- [SQLAlchemy on PyPI](https://pypi.org/project/SQLAlchemy/)
- [pydantic-settings · PyPI](https://pypi.org/project/pydantic-settings/)
- [Settings Management - Pydantic](https://pydantic.dev/docs/validation/latest/concepts/pydantic_settings/)
- [Gunicorn homepage](https://gunicorn.org/)
- [Gunicorn Settings reference](https://gunicorn.org/reference/settings/)
- [gunicorn on PyPI](https://pypi.org/project/gunicorn/)
- [uvicorn · PyPI JSON API](https://pypi.org/pypi/uvicorn/json)
- [uvicorn PyPI project page](https://pypi.org/project/uvicorn/)
- [encode/uvicorn README.md (raw)](https://raw.githubusercontent.com/encode/uvicorn/master/README.md)
- [encode/uvicorn release notes (raw)](https://raw.githubusercontent.com/encode/uvicorn/master/docs/release-notes.md)
- [encode/uvicorn settings docs (fetched via raw markdown)](https://raw.githubusercontent.com/encode/uvicorn/master/docs/settings.md)
- [encode/uvicorn releases (GitHub)](https://github.com/encode/uvicorn/releases)
- [How to use structured outputs with Azure OpenAI in Microsoft Foundry Models](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/structured-outputs)
- [Azure OpenAI reasoning models - GPT-6 Astra and GPT-5 - Microsoft Foundry](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/reasoning)
- [Generate embeddings with Azure OpenAI - Microsoft Foundry](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/embeddings)
- [Truncate Dimensions - Azure AI Search](https://learn.microsoft.com/en-us/azure/search/vector-search-how-to-truncate-dimensions)
- [Azure OpenAI Service Pricing](https://azure.microsoft.com/en-us/pricing/details/cognitive-services/openai-service/)
- [How to use vision-enabled chat models - Microsoft Foundry](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/gpt-with-vision)
- [Azure AI Document Intelligence Pricing](https://azure.microsoft.com/en-us/pricing/details/ai-document-intelligence/)
- [Backup and Restore in Azure Database for PostgreSQL Flexible Server](https://learn.microsoft.com/en-us/azure/postgresql/backup-restore/concepts-backup-restore)
- [Tutorial: Access Azure databases with managed identity - Azure App Service](https://learn.microsoft.com/en-us/azure/app-service/tutorial-connect-msi-azure-database)
- [Azure Container Apps image pull from Azure Container Registry with managed identity](https://learn.microsoft.com/en-us/azure/container-apps/managed-identity-image-pull)
- [Jobs in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/jobs?tabs=azure-cli)
- [Azure built-in roles - AcrPull](https://learn.microsoft.com/en-us/azure/role-based-access-control/built-in-roles#acrpull)
- [Manage secrets in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/manage-secrets)
- [hashes resource type - Microsoft Graph v1.0](https://learn.microsoft.com/en-us/graph/api/resources/hashes)
- [Use delta query to track changes in Microsoft Graph data](https://learn.microsoft.com/en-us/graph/delta-query-overview)
- [Build Python apps with Microsoft Graph and app-only authentication](https://learn.microsoft.com/en-us/graph/tutorials/python-app-only)

## Academic literature

- **OCRVerse: Towards Holistic OCR in End-to-End Vision-Language Models** (2026), cited 18x -- [link](https://doi.org/10.48550/arxiv.2601.21639) / [PDF](https://arxiv.org/pdf/2601.21639) _(via openalex)_
- **Field Order Should Not Matter: Permutation-Invariant Embedding Model Fine-Tuning for Structured Metadata Retrieval** (2026), cited 0x -- [link](https://doi.org/10.48550/arxiv.2606.30473) / [PDF](https://arxiv.org/pdf/2606.30473) _(via openalex)_
- **Algebraic Retrieval: Composable Search for Agents** (2026) -- [link](https://arxiv.org/abs/2609.19482) / [PDF](https://arxiv.org/pdf/2609.19482v1) _(via arxiv)_
- **Digitization of Document and Information Extraction using OCR** (2025) -- [link](https://arxiv.org/abs/2506.11156) / [PDF](https://arxiv.org/pdf/2506.11156v1) _(via arxiv)_
- **Lost in OCR Translation? Vision-Based Approaches to Robust Document Retrieval** (2025) -- [link](https://arxiv.org/abs/2505.05666) / [PDF](https://arxiv.org/pdf/2505.05666v1) _(via arxiv)_
- **Seeing Straight: Document Orientation Detection for Efficient OCR** (2025) -- [link](https://arxiv.org/abs/2511.04161) / [PDF](https://arxiv.org/pdf/2511.04161v2) _(via arxiv)_
- **DocParseNet: Advanced Semantic Segmentation and OCR Embeddings for Efficient Scanned Document Annotation** (2024) -- [link](https://arxiv.org/abs/2406.17591) / [PDF](https://arxiv.org/pdf/2406.17591v3) _(via arxiv)_

## Prior art

_No public repositories matched._

_No public repositories matched the prior-art queries._

## Open uncertainties

- Official documentation: Azure OpenAI Service: `key_findings`
- Official documentation: Azure AI Foundry: `key_findings`
- Official documentation: Azure AI Foundry: `current_version`
- Official documentation: text-embedding-3-large: `key_findings`
- Official documentation: text-embedding-3-large: `pitfalls`
- Official documentation: Azure AI Document Intelligence: `key_findings`
- Official documentation: Azure AI Document Intelligence: `recommendations`
- Official documentation: Azure Database for PostgreSQL Flexible Server: `current_version`
- Official documentation: Azure Database for PostgreSQL Flexible Server: `key_findings`
- Official documentation: pgvector: `key_findings`
- Official documentation: pgvector: `pitfalls`
- Official documentation: pg_trgm: `pitfalls`
- Official documentation: Azure Container Apps: `current_version`
- Official documentation: Microsoft Entra ID: `key_findings`
- Official documentation: Microsoft Entra ID: `pitfalls`
- Official documentation: Bicep: `current_version`
- Official documentation: Bicep: `api_surface`
- Official documentation: Bicep: `key_findings`
- Official documentation: Microsoft Graph API: `pitfalls`
- Official documentation: SharePoint: `key_findings`
- Official documentation: SharePoint: `as_of`
- Official documentation: FastAPI: `pitfalls`
- Official documentation: SQLAlchemy: `key_findings`
- Official documentation: SQLAlchemy: `pitfalls`
- Official documentation: SQLAlchemy: `current_version`
- Official documentation: pydantic-settings: `current_version`
- Official documentation: pydantic-settings: `as_of`
- Official documentation: pydantic-settings: `key_findings`
- Official documentation: gunicorn: `current_version`
- Official documentation: gunicorn: `key_findings`
- Official documentation: uvicorn: `key_findings`
- Official documentation: uvicorn: `as_of`
- Official documentation: uvicorn: `pitfalls`
- Current Azure OpenAI/Foundry models (Nov 2026): `key_findings`
- Current Azure OpenAI/Foundry models (Nov 2026): `recommendations`
- Structured JSON output on Azure OpenAI: `key_findings`
- Structured JSON output on Azure OpenAI: `recommendations`
- Azure embeddings shortened to 768 dims: `summary`
- Azure AI Document Intelligence vs LLM vision OCR: `key_findings`
- Azure AI Document Intelligence vs LLM vision OCR: `recommendations`
- Azure Postgres Flexible Server pgvector+pg_trgm: `key_findings`

## Independent check

Researched by claude-code; checked by claude-code (claude-code (opus) reviewed work written by claude-code (sonnet): the same model family but a different capability class.). Verdict: **pass**.

I opened a representative cross-section of the cited primary sources (pgvector README, Microsoft Graph hashes/tempauth/SharePoint docs, Azure OpenAI embeddings REST ref, Azure Postgres pgvector doc, Container Apps manage-secrets, and PyPI for azure-storage-blob/azure-identity/FastAPI). Every build-critical claim I checked — dimension limits, the 'dimensions' embeddings parameter, the 'vector' extension/allow-list mechanics, sha256 unsupported in Graph hashes, retirement dates, Key Vault reference syntax, and SDK versions/Python floors — matched its source exactly. The report's genuinely speculative items (GPT-6 model families, reasoning_effort matrix, Global/Standard pricing) are flagged as uncertain and sourced from secondary/proxy pages; I could not independently confirm them, so they are unverifiable rather than wrong. The one instruction-looking line in the Container Apps Jobs section was already stripped by the pipeline ('[removed by OSA...]'), so no planted instruction survives into the usable report.

Claims NOT confirmed (treat as uncertain downstream):
- [unverifiable] GPT-6 (Astra/Sol/Luna) and GPT-5.6/5.5/5.4 reasoning models exist with reasoning_effort/mode params, and Global Standard pricing figures (e.g. GPT-6 Astra $10/$50, GPT-5 $1.25/$10). -- The report itself flags these as uncertain and sourced from a text-rendering proxy of the pricing page plus third-party trackers (official pricing page renders JS-only). I could not independently confirm the model lineup or prices; the report hedges appropriately and tells the build to re-check the live calculator. (https://azure.microsoft.com/en-us/pricing/details/cognitive-services/openai-service/)
