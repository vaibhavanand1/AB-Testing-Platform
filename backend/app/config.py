from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql://postgres:postgres@localhost:5432/ab_testing"
    redis_url: str = "redis://localhost:6379/0"
    cache_ttl_seconds: int = 86400
    min_sample_size_per_variant: int = 100
    significance_alpha: float = 0.05

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
