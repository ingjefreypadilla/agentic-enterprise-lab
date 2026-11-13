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
        assert payload["tools"] == main.OLLAMA_TOOLS
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


def test_model_lists_pods_then_gets_bounded_logs(monkeypatch, tmp_path) -> None:
    """Support list-to-logs investigation and return at most 100 actual lines."""
    configure_service_account(monkeypatch, tmp_path)
    ollama_calls = 0
    kubernetes_calls = 0

    def ollama_handler(request: httpx.Request) -> httpx.Response:
        nonlocal ollama_calls
        ollama_calls += 1
        payload = json.loads(request.content)
        if ollama_calls == 1:
            return httpx.Response(200, json=tool_call())
        if ollama_calls == 2:
            list_result = json.loads(payload["messages"][2]["content"])
            assert list_result["pods"][0]["name"] == "worker-abc"
            return httpx.Response(
                200,
                json=tool_call(
                    name="get_pod_logs",
                    arguments={"pod_name": "worker-abc", "tail_lines": 100},
                ),
            )

        log_result = json.loads(payload["messages"][4]["content"])
        assert payload["messages"][4]["tool_name"] == "get_pod_logs"
        assert log_result["namespace"] == "agentic-lab"
        assert log_result["pod_name"] == "worker-abc"
        assert log_result["line_count"] == 100
        assert log_result["logs"].splitlines()[0] == "log-5"
        assert log_result["logs"].splitlines()[-1] == "log-104"
        return httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                    "content": "The worker logs show 100 recent lines.",
                }
            },
        )

    def kubernetes_handler(request: httpx.Request) -> httpx.Response:
        nonlocal kubernetes_calls
        kubernetes_calls += 1
        assert request.headers["Authorization"] == "Bearer test-token"
        if request.url.path == "/api/v1/namespaces/agentic-lab/pods":
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "metadata": {
                                "name": "worker-abc",
                                "namespace": "agentic-lab",
                            },
                            "status": {"phase": "Running"},
                        }
                    ]
                },
            )
        assert request.url.path == (
            "/api/v1/namespaces/agentic-lab/pods/worker-abc/log"
        )
        assert request.url.params["tailLines"] == "100"
        return httpx.Response(200, text="\n".join(f"log-{line}" for line in range(105)))

    response = request_chat(
        ollama_handler,
        kubernetes_handler,
        message="Investigate the worker Pod logs",
    )

    assert response.status_code == 200
    assert response.json() == {
        "response": "The worker logs show 100 recent lines."
    }
    assert ollama_calls == 3
    assert kubernetes_calls == 3


def test_get_pod_logs_recovers_from_missing_pod(
    monkeypatch,
    tmp_path,
    caplog,
) -> None:
    """Return a structured error so Qwen can retry with a current Pod name."""
    configure_service_account(monkeypatch, tmp_path)
    caplog.set_level("INFO", logger=main.__name__)
    ollama_calls = 0

    def ollama_handler(request: httpx.Request) -> httpx.Response:
        nonlocal ollama_calls
        ollama_calls += 1
        payload = json.loads(request.content)
        if ollama_calls == 1:
            return httpx.Response(200, json=tool_call())
        if ollama_calls == 2:
            list_result = json.loads(payload["messages"][2]["content"])
            assert list_result["pods"][0]["name"] == "worker-current"
            return httpx.Response(
                200,
                json=tool_call(
                    name="get_pod_logs",
                    arguments={"pod_name": "missing-pod"},
                ),
            )
        if ollama_calls == 3:
            tool_result = json.loads(payload["messages"][4]["content"])
            assert tool_result == {
                "ok": False,
                "error": {
                    "code": "pod_unavailable",
                    "message": (
                        "The requested Pod is not in the current agentic-lab "
                        "inventory. Choose an exact name from available_pods."
                    ),
                    "retryable": True,
                },
                "requested_pod": "missing-pod",
                "available_pods": ["worker-current"],
            }
            return httpx.Response(
                200,
                json=tool_call(
                    name="get_pod_logs",
                    arguments={"pod_name": "worker-current", "tail_lines": 20},
                ),
            )
        log_result = json.loads(payload["messages"][6]["content"])
        assert log_result["ok"] is True
        assert log_result["logs"] == "worker ready"
        return httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                    "content": "The current worker Pod is ready.",
                }
            },
        )

    def kubernetes_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/namespaces/agentic-lab/pods":
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "metadata": {
                                "name": "worker-current",
                                "namespace": "agentic-lab",
                            },
                            "status": {"phase": "Running"},
                        }
                    ]
                },
            )
        assert request.url.path == (
            "/api/v1/namespaces/agentic-lab/pods/worker-current/log"
        )
        return httpx.Response(200, text="worker ready")

    response = request_chat(ollama_handler, kubernetes_handler)

    assert response.status_code == 200
    assert response.json() == {"response": "The current worker Pod is ready."}
    assert ollama_calls == 4
    tool_logs = "\n".join(record.getMessage() for record in caplog.records)
    assert '"outcome":"pod_unavailable"' in tool_logs
    assert '"outcome":"success"' in tool_logs
    assert '"pod_name":"missing-pod"' in tool_logs
    assert "worker ready" not in tool_logs
    assert "test-token" not in tool_logs


def test_get_pod_logs_recovers_when_pod_disappears(monkeypatch, tmp_path) -> None:
    """Refresh Pod names after a log 404 caused by rollout replacement."""
    configure_service_account(monkeypatch, tmp_path)
    ollama_calls = 0
    kubernetes_calls = 0

    def ollama_handler(request: httpx.Request) -> httpx.Response:
        nonlocal ollama_calls
        ollama_calls += 1
        payload = json.loads(request.content)
        if ollama_calls == 1:
            return httpx.Response(
                200,
                json=tool_call(
                    name="get_pod_logs",
                    arguments={"pod_name": "worker-old"},
                ),
            )
        if ollama_calls == 2:
            tool_result = json.loads(payload["messages"][2]["content"])
            assert tool_result["error"]["code"] == "pod_unavailable"
            assert tool_result["available_pods"] == ["worker-new"]
            return httpx.Response(
                200,
                json=tool_call(
                    name="get_pod_logs",
                    arguments={"pod_name": "worker-new"},
                ),
            )
        return httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                    "content": "The replacement worker is healthy.",
                }
            },
        )

    def pod_list(name: str) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "metadata": {
                            "name": name,
                            "namespace": "agentic-lab",
                        },
                        "status": {"phase": "Running"},
                    }
                ]
            },
        )

    def kubernetes_handler(request: httpx.Request) -> httpx.Response:
        nonlocal kubernetes_calls
        kubernetes_calls += 1
        if kubernetes_calls == 1:
            return pod_list("worker-old")
        if kubernetes_calls == 2:
            assert request.url.path.endswith("/pods/worker-old/log")
            return httpx.Response(404, json={"message": "gone"})
        if kubernetes_calls in {3, 4}:
            return pod_list("worker-new")
        assert request.url.path.endswith("/pods/worker-new/log")
        return httpx.Response(200, text="healthy")

    response = request_chat(ollama_handler, kubernetes_handler)

    assert response.status_code == 200
    assert response.json() == {"response": "The replacement worker is healthy."}
    assert ollama_calls == 3
    assert kubernetes_calls == 5


def test_get_pod_logs_handles_authorization_failure(
    monkeypatch,
    tmp_path,
    caplog,
) -> None:
    """Hide Kubernetes details when access to the logs subresource is denied."""
    configure_service_account(monkeypatch, tmp_path)
    caplog.set_level("INFO", logger=main.__name__)

    def ollama_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=tool_call(
                name="get_pod_logs",
                arguments={"pod_name": "worker-abc", "tail_lines": 20},
            ),
        )

    def kubernetes_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/namespaces/agentic-lab/pods":
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "metadata": {
                                "name": "worker-abc",
                                "namespace": "agentic-lab",
                            },
                            "status": {"phase": "Running"},
                        }
                    ]
                },
            )
        return httpx.Response(403, json={"message": "sensitive RBAC detail"})

    response = request_chat(ollama_handler, kubernetes_handler)

    assert response.status_code == 502
    assert response.json() == {"detail": "Kubernetes API denied the request"}
    tool_logs = "\n".join(record.getMessage() for record in caplog.records)
    assert '"outcome":"failed"' in tool_logs
    assert "sensitive RBAC detail" not in tool_logs


def test_get_pod_logs_rejects_invalid_dns_label() -> None:
    """Reject Pod names with DNS labels longer than Kubernetes permits."""
    invalid_name = f"{'a' * 64}.worker"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=tool_call(
                name="get_pod_logs",
                arguments={"pod_name": invalid_name},
            ),
        )

    response = request_chat(handler)

    assert response.status_code == 502
    assert response.json() == {
        "detail": "Model requested an unauthorized tool operation"
    }


def test_get_pod_logs_rejects_more_than_100_lines() -> None:
    """Reject a model request that exceeds the hard log-line bound."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=tool_call(
                name="get_pod_logs",
                arguments={"pod_name": "worker-abc", "tail_lines": 101},
            ),
        )

    response = request_chat(handler)

    assert response.status_code == 502
    assert response.json() == {
        "detail": "Model requested an unauthorized tool operation"
    }


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
