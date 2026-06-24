import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import AuthUser, get_current_user
from app.main import app


def _auth_override() -> AuthUser:
    return AuthUser(id="test-user-id", email="analyst@driftwood.com")


@pytest.fixture
def client():
    app.dependency_overrides[get_current_user] = _auth_override
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def unauth_client():
    yield TestClient(app)


def test_stream_requires_auth(unauth_client):
    response = unauth_client.post(
        "/chat/stream",
        json={"thread_id": "test-thread", "messages": []},
    )
    assert response.status_code == 403


def test_stream_returns_200_with_ai_sdk_headers(client):
    response = client.post(
        "/chat/stream",
        json={"thread_id": "test-thread", "messages": [{"role": "user", "content": "hello"}]},
        headers={"Authorization": "Bearer fake-token"},
    )
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert response.headers.get("x-vercel-ai-data-stream") == "v1"


def test_stream_body_contains_data_stream_parts(client):
    response = client.post(
        "/chat/stream",
        json={"thread_id": "test-thread", "messages": [{"role": "user", "content": "hello"}]},
        headers={"Authorization": "Bearer fake-token"},
    )
    lines = response.text.splitlines()
    # At least one text part
    assert any(line.startswith('0:"') for line in lines), "missing text part (0:)"
    # Finish event
    assert any(line.startswith("e:") for line in lines), "missing finish event (e:)"
    # Data finish
    assert any(line.startswith("d:") for line in lines), "missing data finish (d:)"
