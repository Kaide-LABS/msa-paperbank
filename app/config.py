import os
from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # Provider seam (Phase 1): selects which adapters the factory returns. Only "gcp"
    # is valid this phase; "local"/"minio" arrive in later phases. Env: PROVIDER.
    provider: str = "gcp"
    gcp_project: str
    gcp_location: str = "global"
    cloud_sql_instance: str
    db_user: str
    db_password: SecretStr
    db_name: str = "paperbank"
    gcs_bucket: str
    wa_phone_number_id: str
    wa_access_token: SecretStr
    wa_app_secret: SecretStr
    wa_verify_token: SecretStr
    wa_graph_version: str = "v23.0"
    model_flash: str = "gemini-3-flash-preview"
    model_pro: str = "gemini-3.1-pro-preview"
    hardcoded_course_code: str = "MTH102"
    request_rate_limit_per_hour: int = 300
    log_level: str = "INFO"
    model_embedding: str = "gemini-embedding-001"
    embedding_dim: int = 768
    ocr_max_image_bytes: int = 7_000_000
    ocr_max_images_per_paper: int = 12
    # Decision 2 (2026-06 OCR probe): cv2 preprocessing improved 0/12 sampled files and was
    # net-negative on degraded inputs (one hard MAX_TOKENS failure, one mis-numbering). Raw
    # bytes now go straight to OCR. Left as an off-by-default flag (not deleted) so preprocess
    # can earn its way back via an explicit A/B. See app.preprocess.prepare_images_for_ocr.
    ocr_preprocess_enabled: bool = False
    embedding_concurrency: int = 8
    semantic_fallback_top_k: int = 3
    semantic_fallback_min_router_confidence: float = 0.5
    daily_cost_usd_cap: float = 0.50
    daily_token_floor: int = Field(
        200_000,
        validation_alias=AliasChoices("daily_token_floor", "daily_token_budget"),
    )
    price_flash_input_per_1m_usd: float = 0.50
    price_flash_output_per_1m_usd: float = 3.00
    price_pro_input_per_1m_usd: float = 2.00
    price_pro_output_per_1m_usd: float = 12.00
    price_embedding_per_1m_usd: float = 0.05
    admin_bearer_token: SecretStr | None = None
    drive_default_folder_id: str | None = None
    drive_service_account_json: str | None = None
    course_catalog_cache_seconds: int = 60
    unknown_course_suggest_count: int = 3
    image_batch_seal_seconds: int = 90
    image_intake_ocr_per_day: int = 100
    image_intake_max_open_batches_per_phone_per_day: int = 3
    media_gcs_prefix: str = "media/"
    personalization_min_interactions: int = 5
    personalization_tie_band: float = 0.05
    personalization_top_k_for_bias: int = 2
    # Dual-read consensus (app.validator): fraction of FULL-AGREEMENT papers pulled for a human
    # spot-check instead of blind auto-accept. Selection is DETERMINISTIC by paper sha (reproducible,
    # not random per run). Insurance against SHARED omissions both reads miss (trial: GST111 skipped
    # the same question in both reads). 0.15 = 15%.
    spotcheck_rate: float = 0.15
    # Change A: serve the gentle, diagram-safe DISPLAY enhancement (auto_rotate + enhance_for_display)
    # on retrieval. ON-THE-FLY from the stored RAW by default (raw stays the single source of truth,
    # no migration). Flip to False to serve raw unchanged, or move enhancement to ingest-time (see
    # app.retrieval.render_served_pdf). OCR path is unaffected — it reads raw upstream.
    serve_enhance_enabled: bool = True
    # Dual-read routing mode (app.validator.compare_reads). "index" = OCR is an internal SEARCH
    # INDEX (students receive the enhanced IMAGE, not OCR text), so only retrievability + filing
    # metadata gate; numeric/question-count disagreements are diagnostics, not human work.
    # "publish" = the old text-trust gating (numeric/structure -> curation). Kept for comparison.
    curation_mode: str = "index"
    # --- V1 serving bridge (app.serve_v1 / app.serve_index): retrieval directly over the
    # corpus-index pending_papers (student_visible), NO promotion into the normalized schema. ---
    serve_v1_enabled: bool = True                 # main.py routes to the lean V1 handler
    serve_source_tag: str = "corpus_full"         # which ingest source the bot serves
    serve_fuzzy_threshold: float = 0.30           # pg_trgm similarity floor for L2 title/slug match
    serve_candidate_k: int = 8                    # L2 fuzzy candidates fetched before narrowing
    serve_dominance_gap: float = 0.15             # top-vs-second score gap to auto-serve without disambiguation
    serve_max_candidates: int = 5                 # disambiguation list length cap
    serve_clean_miss_enabled: bool = True         # A1: a weak CLUSTER (no clear winner) -> honest miss, not junk list
    serve_confident_bar: float = 0.45             # A1: top fuzzy score below this (and clustered) => miss
    serve_fallback_disambiguate_enabled: bool = True  # A3: cross-school fallback never auto-serves; always disambiguate
    serve_hybrid_enabled: bool = True             # B: semantic re-ranks the FUZZY-surfaced candidates (consensus layer)
    serve_semantic_bar: float = 0.70              # B: semantic-'strong' bar for the re-rank role (tuned vs absent-vs-paraphrase)
    serve_skip_embed_when_dominant: bool = True   # latency: skip the embed when fuzzy is already decisive (outcome-identical)
    serve_skip_dominant_bar: float = 1.0          # skip only when top fuzzy >= this AND dominates (tuned for zero divergence)
    serve_precompute_enabled: bool = True         # hardening: serve the pre-rendered served/ PDF (download) instead of live-rendering; falls back to live render if absent
    serve_precompute_prefix: str = "served/"      # GCS prefix for the pre-rendered enhanced PDFs
    serve_session_ttl_seconds: int = 900          # how long a tap-to-choose list stays resolvable
    serve_school_scoping_enabled: bool = True      # V1.1: per-student school profile + school-scoped match
    serve_onboarding_ttl_seconds: int = 1800       # how long a pending school-onboarding prompt stays resolvable
    serve_multipage_enabled: bool = True           # V1.2: assemble grouped page-rows into one multi-page exam PDF
    # Build 2: WhatsApp contribution intake (students photograph papers -> bot validates/collects ->
    # awaiting_review queue; NOTHING student-visible until the Build-3 web app approves).
    serve_contributions_enabled: bool = True
    contribution_gcs_prefix: str = "contributions/"   # contributed raw images, separate from corpus_full/
    contribution_weekly_cap: int = 20                 # accepted finalized sessions per rolling 7 days (general public)
    contribution_idle_seconds: int = 90               # idle before the sweep checks in / finalizes a collecting session
    contribution_max_pages: int = 20                  # safety cap on pages per contribution
    contribution_max_image_bytes: int = 10_000_000
    # Build 3: review web app (separate paperbank-review service; same DB + bucket).
    review_session_secret: SecretStr | None = None    # HMAC key for the signed session cookie
    review_session_hours: int = 10
    review_otp_ttl_seconds: int = 300                 # 5 min
    review_otp_max_attempts: int = 5                  # lock after N wrong tries
    review_otp_resend_seconds: int = 30               # min gap between code requests
    review_promoted_prefix: str = "contributed/"      # approved contributed images live here (served)

def load_settings_with_secret_manager() -> Settings:
    if os.environ.get("GCP_LOAD_FROM_SECRETS") != "1":
        return Settings()

    from app.providers import get_secrets_provider

    secrets = get_secrets_provider()
    for key, value in os.environ.items():
        if key.endswith("_FROM_SECRET"):
            actual_key = key.replace("_FROM_SECRET", "")
            os.environ[actual_key] = secrets.get(value)

    return Settings()

settings = load_settings_with_secret_manager()