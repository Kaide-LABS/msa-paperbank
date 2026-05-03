import os
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from google.cloud import secretmanager

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)
    
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
    embedding_concurrency: int = 8
    semantic_fallback_top_k: int = 3
    semantic_fallback_min_router_confidence: float = 0.5
    daily_token_budget: int = 200_000
    admin_bearer_token: SecretStr | None = None
    drive_default_folder_id: str | None = None
    drive_service_account_json: str | None = None
    course_catalog_cache_seconds: int = 60
    unknown_course_suggest_count: int = 3

def load_settings_with_secret_manager() -> Settings:
    if os.environ.get("GCP_LOAD_FROM_SECRETS") != "1":
        return Settings()
    
    client = secretmanager.SecretManagerServiceClient()
    for key, value in os.environ.items():
        if key.endswith("_FROM_SECRET"):
            actual_key = key.replace("_FROM_SECRET", "")
            response = client.access_secret_version(name=value)
            payload = response.payload.data.decode("UTF-8")
            os.environ[actual_key] = payload
            
    return Settings()

settings = load_settings_with_secret_manager()