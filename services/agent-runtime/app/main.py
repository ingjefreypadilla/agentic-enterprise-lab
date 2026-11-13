import json
import os
import re
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Annotated, Any

import httpx
from fastapi import Depends, FastAPI, HTTPException, status
from pydantic import BaseModel, Field

DEFAULT_OLLAMA_BASE_URL = "http://192.168.1.73:11434"
DEFAULT_OLLAMA_MODEL = "qwen3.5:9b-16k"
OLLAMA_TIMEOUT = httpx.Timeout(120.0, connect=5.0)
KUBERNETES_TIMEOUT = httpx.Timeout(5.0, connect=2.0)
KUBERNETES_NAMESPACE = "agentic-lab"
SERVICE_ACCOUNT_DIRECTORY = Path("/var/run/secrets/kubernetes.io/serviceaccount")
MAX_TOOL_CALLS = 3
MAX_LOG_LINES = 100
POD_NAME_PATTERN = re.compile(
    r"^[a-z0-9](?:[-a-z0-9]*[a-z0-9])?"
    r"(?:\.[a-z0-9](?:[-a-z0-9]*[a-z0-9])?)*$"
)
ALLOWED_TOOLS = frozenset({"list_pods", "get_pod_logs"})

LIST_PODS_TOOL = {
    "type": "function",
    "function": {
        "name": "list_pods",
        "description": "List Pods in the agentic-lab Kubernetes namespace.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    },
}

GET_POD_LOGS_TOOL = {
    "type": "function",
    "function": {
        "name": "get_pod_logs",
        "description": (
            "Get up to 100 recent log lines from an existing Pod in the "
            "agentic-lab Kubernetes namespace."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pod_name": {
                    "type": "string",
                    "description": "Exact Pod name returned by list_pods.",
                    "maxLength": 253,
                    "pattern": (
                        "^[a-z0-9](?:[-a-z0-9]*[a-z0-9])?"
                        "(?:\\.[a-z0-9](?:[-a-z0-9]*[a-z0-9])?)*$"
                    ),
                },
                "tail_lines": {
                    "type": "integer",
                    "description": "Number of recent log lines to retrieve.",
                    "minimum": 1,
                    "maximum": MAX_LOG_LINES,
                    "default": MAX_LOG_LINES,
                },
            },
            "required": ["pod_name"],
            "additionalProperties": False,
        },
    },
}

OLLAMA_TOOLS = [LIST_PODS_TOOL, GET_POD_LOGS_TOOL]

app = FastAPI(
    title="Agent Runtime Service",
    description="A minimal Ollama-backed chat service for the Agentic Enterprise Lab",
    version="0.3.0",
)


class ChatRequest(BaseModel):
    """User chat request."""

    message: str = Field(min_length=1)


class ChatResponse(BaseModel):
    """Sanitized model response."""

    response: str


async def get_ollama_client() -> AsyncIterator[httpx.AsyncClient]:
    """Provide an HTTP client for Ollama requests."""
    async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as client:
        yield client


async def get_kubernetes_client() -> AsyncIterator[httpx.AsyncClient]:
    """Provide a short-lived client that trusts the in-cluster Kubernetes CA."""
    ca_path = SERVICE_ACCOUNT_DIRECTORY / "ca.crt"
    verify: bool | str = str(ca_path) if ca_path.is_file() else True
    async with httpx.AsyncClient(timeout=KUBERNETES_TIMEOUT, verify=verify) as client:
        yield client


OllamaClient = Annotated[httpx.AsyncClient, Depends(get_ollama_client)]
KubernetesClient = Annotated[httpx.AsyncClient, Depends(get_kubernetes_client)]


@app.get("/health")
def health_check() -> dict:
    """Health check endpoint."""
    return {"status": "healthy"}


def ollama_configuration() -> tuple[str, str]:
    """Return the configured Ollama endpoint and model."""
    base_url = os.getenv("OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL).rstrip("/")
    model = os.getenv("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL)
    return base_url, model


async def request_ollama(
    client: httpx.AsyncClient,
    messages: list[dict[str, Any]],
) -> dict[str, Any]:
    """Send one tool-aware chat turn to Ollama and validate its envelope."""
    base_url, model = ollama_configuration()
    try:
        upstream = await client.post(
            f"{base_url}/api/chat",
            json={
                "model": model,
                "messages": messages,
                "tools": OLLAMA_TOOLS,
                "stream": False,
            },
        )
        upstream.raise_for_status()
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Ollama request timed out",
        ) from exc
    except (httpx.RequestError, httpx.HTTPStatusError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Ollama request failed",
        ) from exc

    try:
        payload = upstream.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Ollama returned an invalid response",
        ) from exc

    message = payload.get("message") if isinstance(payload, dict) else None
    if not isinstance(message, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Ollama returned an invalid response",
        )
    return message


def kubernetes_api_url() -> str:
    """Build the in-cluster API URL without allowing a namespace override."""
    host = os.getenv("KUBERNETES_SERVICE_HOST", "kubernetes.default.svc")
    port = os.getenv("KUBERNETES_SERVICE_PORT_HTTPS", "443")
    return f"https://{host}:{port}"


async def list_pods(client: httpx.AsyncClient) -> dict[str, Any]:
    """List a sanitized view of Pods in the one authorized namespace."""
    try:
        token = (SERVICE_ACCOUNT_DIRECTORY / "token").read_text().strip()
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Kubernetes service account is unavailable",
        ) from exc

    try:
        upstream = await client.get(
            f"{kubernetes_api_url()}/api/v1/namespaces/{KUBERNETES_NAMESPACE}/pods",
            headers={"Authorization": f"Bearer {token}"},
        )
        upstream.raise_for_status()
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Kubernetes API request timed out",
        ) from exc
    except httpx.HTTPStatusError as exc:
        detail = (
            "Kubernetes API denied the request"
            if exc.response.status_code in {401, 403}
            else "Kubernetes API request failed"
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=detail,
        ) from exc
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Kubernetes API request failed",
        ) from exc

    try:
        payload = upstream.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Kubernetes API returned an invalid response",
        ) from exc

    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Kubernetes API returned an invalid response",
        )

    pods = []
    for item in items:
        metadata = item.get("metadata") if isinstance(item, dict) else None
        pod_status = item.get("status") if isinstance(item, dict) else None
        name = metadata.get("name") if isinstance(metadata, dict) else None
        namespace = metadata.get("namespace") if isinstance(metadata, dict) else None
        phase = pod_status.get("phase") if isinstance(pod_status, dict) else None
        if (
            not isinstance(name, str)
            or namespace != KUBERNETES_NAMESPACE
            or not isinstance(phase, str)
        ):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Kubernetes API returned an invalid response",
            )
        pods.append({"name": name, "namespace": namespace, "phase": phase})
    return {"namespace": KUBERNETES_NAMESPACE, "count": len(pods), "pods": pods}


async def get_pod_logs(
    client: httpx.AsyncClient,
    pod_name: str,
    tail_lines: int,
) -> dict[str, Any]:
    """Return bounded logs only after confirming the Pod currently exists."""
    pod_listing = await list_pods(client)
    existing_pods = {pod["name"] for pod in pod_listing["pods"]}
    if pod_name not in existing_pods:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Requested Pod is unavailable",
        )

    try:
        token = (SERVICE_ACCOUNT_DIRECTORY / "token").read_text().strip()
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Kubernetes service account is unavailable",
        ) from exc

    try:
        upstream = await client.get(
            (
                f"{kubernetes_api_url()}/api/v1/namespaces/"
                f"{KUBERNETES_NAMESPACE}/pods/{pod_name}/log"
            ),
            headers={"Authorization": f"Bearer {token}"},
            params={"tailLines": tail_lines},
        )
        upstream.raise_for_status()
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Kubernetes API request timed out",
        ) from exc
    except httpx.HTTPStatusError as exc:
        detail = (
            "Kubernetes API denied the request"
            if exc.response.status_code in {401, 403}
            else "Kubernetes API request failed"
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=detail,
        ) from exc
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Kubernetes API request failed",
        ) from exc

    log_lines = upstream.text.splitlines()[-tail_lines:]
    return {
        "namespace": KUBERNETES_NAMESPACE,
        "pod_name": pod_name,
        "line_count": len(log_lines),
        "logs": "\n".join(log_lines),
    }


def validated_tool_calls(message: dict[str, Any]) -> list[dict[str, Any]]:
    """Validate model-selected calls against the strict server-side allowlist."""
    tool_calls = message.get("tool_calls", [])
    if not isinstance(tool_calls, list):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Ollama returned an invalid response",
        )

    validated = []
    for tool_call in tool_calls:
        function = tool_call.get("function") if isinstance(tool_call, dict) else None
        name = function.get("name") if isinstance(function, dict) else None
        arguments = function.get("arguments", {}) if isinstance(function, dict) else None
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except ValueError:
                arguments = None
        if name not in ALLOWED_TOOLS or not isinstance(arguments, dict):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Model requested an unauthorized tool operation",
            )
        if name == "list_pods":
            if arguments != {}:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Model requested an unauthorized tool operation",
                )
            validated_arguments = {}
        else:
            pod_name = arguments.get("pod_name")
            tail_lines = arguments.get("tail_lines", MAX_LOG_LINES)
            if (
                set(arguments) - {"pod_name", "tail_lines"}
                or not isinstance(pod_name, str)
                or len(pod_name) > 253
                or POD_NAME_PATTERN.fullmatch(pod_name) is None
                or isinstance(tail_lines, bool)
                or not isinstance(tail_lines, int)
                or not 1 <= tail_lines <= MAX_LOG_LINES
            ):
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Model requested an unauthorized tool operation",
                )
            validated_arguments = {
                "pod_name": pod_name,
                "tail_lines": tail_lines,
            }
        validated.append(
            {"function": {"name": name, "arguments": validated_arguments}}
        )
    return validated


@app.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    ollama_client: OllamaClient,
    kubernetes_client: KubernetesClient,
) -> ChatResponse:
    """Let Ollama select an allowed tool and summarize its actual output."""
    messages: list[dict[str, Any]] = [{"role": "user", "content": request.message}]
    tool_call_count = 0

    while True:
        assistant_message = await request_ollama(ollama_client, messages)
        tool_calls = validated_tool_calls(assistant_message)
        if not tool_calls:
            content = assistant_message.get("content")
            if not isinstance(content, str):
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Ollama returned an invalid response",
                )
            return ChatResponse(response=content)

        if tool_call_count + len(tool_calls) > MAX_TOOL_CALLS:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Model exceeded the tool-call limit",
            )
        tool_call_count += len(tool_calls)
        assistant_content = assistant_message.get("content", "")
        if not isinstance(assistant_content, str):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Ollama returned an invalid response",
            )
        messages.append(
            {
                "role": "assistant",
                "content": assistant_content,
                "tool_calls": tool_calls,
            }
        )
        for tool_call in tool_calls:
            function = tool_call["function"]
            if function["name"] == "list_pods":
                result = await list_pods(kubernetes_client)
            else:
                result = await get_pod_logs(
                    kubernetes_client,
                    function["arguments"]["pod_name"],
                    function["arguments"]["tail_lines"],
                )
            messages.append(
                {
                    "role": "tool",
                    "tool_name": function["name"],
                    "content": json.dumps(result, separators=(",", ":")),
                }
            )
