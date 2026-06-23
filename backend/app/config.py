from typing import Tuple, Type

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings.main import PydanticBaseSettingsSource


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str
    database_url: str
    openai_api_key: str
    openai_embedding_model: str = "text-embedding-3-small"
    openai_embedding_dimensions: int = 1536
    # Comma-separated string so env files don't need JSON array syntax.
    # main.py splits this into a list for the CORS middleware.
    allowed_origins: str = "http://localhost:5173"

    @field_validator("database_url", mode="before")
    @classmethod
    def fix_database_url_scheme(cls, v: str) -> str:
        # Supabase provides postgresql:// URLs; psycopg3 requires postgresql+psycopg://
        if isinstance(v, str) and v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+psycopg://", 1)
        return v

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> Tuple[PydanticBaseSettingsSource, ...]:
        # When _env_file=None is passed explicitly (e.g. in tests), only use
        # init kwargs — skip env and dotenv so tests control all values.
        if getattr(dotenv_settings, "env_file", "sentinel") is None:
            return (init_settings,)
        return init_settings, env_settings, dotenv_settings, file_secret_settings


settings = Settings()
