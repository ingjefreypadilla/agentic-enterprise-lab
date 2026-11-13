import asyncio
import json

import httpx

from app import main
from app.main import app, get_kubernetes_client, get_ollama_client


async def request(method: str, path: str, **kwargs) -> httpx.Response:
    """Send a request to the ASGI application."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        return await client.request(method, path, **kwargs)


def request_chat(
    ollama_handler,
    kubernetes_handler=None,
    message: str = "Hello",
) -> httpx.Response:
    """Send a chat request with mocked Ollama and Kubernetes transports."""
    if kubernetes_handler is None:
        def kubernetes_handler(request: httpx.Request) -> httpx.Response:
            raise AssertionError(f"Unexpected Kubernetes request: {request.url}")

    async def override_ollama_client():
        transport = httpx.MockTransport(ollama_handler)
        async with httpx.AsyncClient(transport=transport) as client:
            yield client

    async def override_kubernetes_client():
        transport = httpx.MockTransport(kubernetes_handler)
        async with httpx.AsyncClient(transport=transport) as client:
            yield client

    app.dependency_overrides[get_ollama_client] = override_ollama_client
    app.dependency_overrides[get_kubernetes_client] = override_kubernetes_client
    try:
        return asyncio.run(request("POST", "/chat", json={"message": message}))
    finally:
        app.dependency_overrides.clear()


def configure_service_account(monkeypatch, tmp_path) -> None:
    """Point service-account reads at a temporary test token."""
    (tmp_path / "token").write_text("test-token\n")
    monkeypatch.setattr(main, "SERVICE_ACCOUNT_DIRECTORY", tmp_path)


def tool_call(name: str = "list_pods", arguments=None) -> dict:
    """Build an Ollama tool-call response."""
    if arguments is None:
        arguments = {}
    return {
        "message": {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"function": {"name": name, "arguments": arguments}},
            ],
        }
    }


def test_health_check() -> None:
    """Test the health check endpoint returns healthy status."""
    response = asyncio.run(request("GET", "/health"))

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_chat_returns_only_response_field(monkeypatch) -> None:
    """Return only model content and use the lab defaults."""
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "http://192.168.1.73:11434/api/chat"
        payload = json.loads(request.content)
        assert payload["model"] == "qwen3.5:9b-16k"
        assert payload["messages"] == [{"role": "user", "content": "Hello"}]
        assert payload["tools"] == [main.LIST_PODS_TOOL]
        assert payload["stream"] is False
        return httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                    "content": "Hello from Ollama",
                    "thinking": "internal reasoning",
                },
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
        assert str(request.url) == "http://ollama.test:11434/api/chat"
        assert json.loads(request.content)["model"] == "test-model"
        return httpx.Response(
            200,
            json={"message": {"role": "assistant", "content": "Configured"}},
        )

    response = request_chat(handler)

    assert response.status_code == 200
    assert response.json() == {"response": "Configured"}


def test_model_calls_list_pods_and_summarizes_results(monkeypatch, tmp_path) -> None:
    """Give actual namespace-scoped Pod results back to Qwen for summarization."""
    configure_service_account(monkeypatch, tmp_path)
    ollama_calls = 0

    def ollama_handler(request: httpx.Request) -> httpx.Response:
        nonlocal ollama_calls
        ollama_calls += 1
        payload = json.loads(request.content)
        if ollama_calls == 1:
            return httpx.Response(200, json=tool_call())

        assert payload["messages"][1]["tool_calls"] == [
            {"function": {"name": "list_pods", "arguments": {}}}
        ]
        result = json.loads(payload["messages"][2]["content"])
        assert payload["messages"][2]["tool_name"] == "list_pods"
        assert result == {
            "namespace": "agentic-lab",
            "count": 1,
            "pods": [
                {
                    "name": "agent-runtime-abc",
                    "namespace": "agentic-lab",
                    "phase": "Running",
                }
            ],
        }
        return httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                    "content": "One Pod is running: agent-runtime-abc.",
                }
            },
        )

    def kubernetes_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/namespaces/agentic-lab/pods"
        assert request.headers["Authorization"] == "Bearer test-token"
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "metadata": {
                            "name": "agent-runtime-abc",
                            "namespace": "agentic-lab",
                        },
                        "status": {"phase": "Running"},
                    }
                ]
            },
        )

    response = request_chat(
        ollama_handler,
        kubernetes_handler,
        message="Which Pods are running?",
    )

    assert response.status_code == 200
    assert response.json() == {
        "response": "One Pod is running: agent-runtime-abc."
    }
    assert ollama_calls == 2


def test_chat_rejects_unallowlisted_tool() -> None:
    """Never execute a tool that is absent from the server-side allowlist."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=tool_call(name="delete_pod"))

    response = request_chat(handler)

    assert response.status_code == 502
    assert response.json() == {
        "detail": "Model requested an unauthorized tool operation"
    }


def test_chat_rejects_namespace_override() -> None:
    """Reject arguments that try to escape the fixed namespace."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=tool_call(arguments={"namespace": "kube-system"}),
        )

    response = request_chat(handler)

    assert response.status_code == 502
    assert response.json() == {
        "detail": "Model requested an unauthorized tool operation"
    }


def test_chat_enforces_tool_call_limit(monkeypatch, tmp_path) -> None:
    """Stop a model that repeatedly requests allowed tools."""
    configure_service_account(monkeypatch, tmp_path)

    def ollama_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=tool_call())

    def kubernetes_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"items": []})

    response = request_chat(ollama_handler, kubernetes_handler)

    assert response.status_code == 502
    assert response.json() == {"detail": "Model exceeded the tool-call limit"}


def test_chat_handles_kubernetes_api_failure(monkeypatch, tmp_path) -> None:
    """Return a sanitized error when the Kubernetes API fails."""
    configure_service_account(monkeypatch, tmp_path)

    def ollama_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=tool_call())

    def kubernetes_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"message": "internal cluster detail"})

    response = request_chat(ollama_handler, kubernetes_handler)

    assert response.status_code == 502
    assert response.json() == {"detail": "Kubernetes API request failed"}


def test_chat_handles_kubernetes_timeout(monkeypatch, tmp_path) -> None:
    """Enforce the Kubernetes deadline and return a gateway timeout."""
    configure_service_account(monkeypatch, tmp_path)

    def ollama_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=tool_call())

    def kubernetes_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    response = request_chat(ollama_handler, kubernetes_handler)

    assert response.status_code == 504
    assert response.json() == {"detail": "Kubernetes API request timed out"}


def test_chat_handles_kubernetes_rbac_denial(monkeypatch, tmp_path) -> None:
    """Do not expose Kubernetes details when the ServiceAccount is unauthorized."""
    configure_service_account(monkeypatch, tmp_path)

    def ollama_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=tool_call())

    def kubernetes_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"message": "RBAC details"})

    response = request_chat(ollama_handler, kubernetes_handler)

    assert response.status_code == 502
    assert response.json() == {"detail": "Kubernetes API denied the request"}


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
    """Reject responses without a message object."""
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
