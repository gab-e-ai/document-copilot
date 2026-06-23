import os

# Set fake env vars before any app module is imported.
# Using setdefault means real env vars (e.g., CI secrets) are not overwritten.
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-key")
