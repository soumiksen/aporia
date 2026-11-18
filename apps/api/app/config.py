from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../../.env"), extra="ignore")

    database_url: str = "postgresql+asyncpg://aporia:aporia@localhost:5432/aporia"
    redis_url: str = "redis://localhost:6379/0"
    judge0_url: str = "http://localhost:2358"
    aporia_env: str = "dev"


def get_settings() -> Settings:
    return Settings()
