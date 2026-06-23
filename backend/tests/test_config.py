import pytest
from pydantic import ValidationError

from app.config import Settings


def test_settings_loads_with_explicit_values():
    s = Settings(
        supabase_url="https://abc.supabase.co",
        supabase_anon_key="anon",
        supabase_service_role_key="service",
        database_url="postgresql://user:pass@localhost/db",
        openai_api_key="sk-test",
        _env_file=None,
    )
    assert s.openai_embedding_model == "text-embedding-3-small"
    assert s.openai_embedding_dimensions == 1536
    assert s.allowed_origins == "http://localhost:5173"


def test_settings_missing_required_raises():
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_parses_allowed_origins_list():
    s = Settings(
        supabase_url="https://abc.supabase.co",
        supabase_anon_key="anon",
        supabase_service_role_key="service",
        database_url="postgresql://user:pass@localhost/db",
        openai_api_key="sk-test",
        allowed_origins="http://localhost:5173,http://localhost:3000",
        _env_file=None,
    )
    assert len(s.allowed_origins.split(",")) == 2
