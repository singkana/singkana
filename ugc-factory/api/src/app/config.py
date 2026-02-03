from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "dev"
    database_url: str
    redis_url: str = "redis://localhost:6379/0"

    api_key: str = "dev_api_key_change_me"

    llm_provider: str = "openai"
    openai_api_key: str | None = None
    llm_model: str = "gpt-4o-mini"

    tts_provider: str = "openai"
    openai_tts_model: str = "gpt-4o-mini-tts"
    elevenlabs_api_key: str | None = None
    tts_max_chars: int = 800

    video_provider: str = "dummy"
    heygen_api_key: str | None = None
    heygen_avatar_id: str | None = None
    heygen_poll_timeout_sec: int = 600

    finalize_provider: str = "worker"
    redis_queue_key: str = "ugc:finalize"
    finalize_internal_token: str | None = None

    s3_endpoint: str
    s3_bucket: str
    s3_access_key: str
    s3_secret_key: str
    s3_region: str = "us-east-1"

    max_retries: int = 3
    idempotency_ttl_sec: int = 86400


settings = Settings()

