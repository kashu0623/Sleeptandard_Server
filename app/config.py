from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Wearable Sleep API"
    database_url: str = (
        "postgresql+psycopg://wearable:wearable@localhost:5432/wearable_sleep"
    )
    api_key: str = "local-dev-api-key"
    access_token_secret_key: str = "local-dev-access-token-secret-change-me"
    access_token_expires_minutes: int = 60 * 24 * 7
    aws_region: str = "ap-northeast-2"
    # When deployed to AWS, leave these unset so boto3 uses the instance role.
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    aws_session_token: str | None = None
    aws_s3_endpoint_url: str | None = None
    s3_bucket_name: str = "wearable-sleep-local"
    s3_upload_url_expires_sec: int = 900
    s3_multipart_backend: str = "local"
    public_base_url: str = "http://127.0.0.1:8000"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
