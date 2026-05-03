from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

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

settings = Settings()