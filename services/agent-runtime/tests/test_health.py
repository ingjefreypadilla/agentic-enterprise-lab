import asyncio
import json

import httpx

from app.main import app, get_ollama_client


async def request(method: str, path: str, **kwargs) -> httpx.Response:
    """Send a request to the ASGI application."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        return await client.request(method, path, **kwargs)


def request_chat(handler, message: str = "Hello") -> httpx.Response:
    """Send a chat request with a mocked Ollama transport."""
    transport = httpx.MockTransport(handler)

    async def override_ollama_client():
        async with httpx.AsyncClient(transport=transport) as client:
            yield client

    app.dependency_overrides[get_ollama_client] = override_ollama_client
    try:
        return asyncio.run(request("POST", "/chat", json={"message": message}))
    finally:
        app.dependency_overrides.clear()


def test_health_check() -> None:
    """Test the health check endpoint returns healthy status."""
    response = asyncio.run(request("GET", "/health"))

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_chat_returns_only_response_field(monkeypatch) -> None:
    """Return only the model response and use the lab defaults."""
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "http://192.168.1.73:11434/api/generate"
        assert json.loads(request.content) == {
            "model": "qwen3.5:9b-16k",
            "prompt": "Hello",
            "stream": False,
        }
        return httpx.Response(
            200,
            json={
                "response": "Hello from Ollama",
                "thinking": "internal reasoning",
                "done": True,
            },
        )

    response = request_chat(handler)

    assert response.status_code == 200
    assert response.json() == {"response": "Hello from Ollama"}


def test_chat_uses_environment_configuration(monkeypatch) -> None:
    """Use configured Ollama URL and model values."""
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama.test:11434/")
    monkeypatch.setenv("OLLAMA_MODEL", "test-model")

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "http://ollama.test:11434/api/generate"
        assert json.loads(request.content)["model"] == "test-model"
        return httpx.Response(200, json={"response": "Configured"})

    response = request_chat(handler)

    assert response.status_code == 200
    assert response.json() == {"response": "Configured"}


def test_chat_handles_ollama_timeout() -> None:
    """Return a gateway timeout when Ollama times out."""
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    response = request_chat(handler)

    assert response.status_code == 504
    assert response.json() == {"detail": "Ollama request timed out"}


def test_chat_handles_connection_error() -> None:
    """Return a bad gateway when Ollama cannot be reached."""
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection failed", request=request)

    response = request_chat(handler)

    assert response.status_code == 502
    assert response.json() == {"detail": "Ollama request failed"}


def test_chat_hides_ollama_error_body() -> None:
    """Do not expose upstream errors or internal metadata."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            500,
            json={"error": "upstream detail", "thinking": "internal reasoning"},
        )

    response = request_chat(handler)

    assert response.status_code == 502
    assert response.json() == {"detail": "Ollama request failed"}


def test_chat_rejects_invalid_ollama_response() -> None:
    """Reject responses without a string response field."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"thinking": "internal reasoning"})

    response = request_chat(handler)

    assert response.status_code == 502
    assert response.json() == {"detail": "Ollama returned an invalid response"}


def test_chat_rejects_non_json_ollama_response() -> None:
    """Reject non-JSON upstream responses."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not json")

    response = request_chat(handler)

    assert response.status_code == 502
    assert response.json() == {"detail": "Ollama returned an invalid response"}
