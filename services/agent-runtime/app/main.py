import os
from collections.abc import AsyncIterator
from typing import Annotated

import httpx
from fastapi import Depends, FastAPI, HTTPException, status
from pydantic import BaseModel, Field

DEFAULT_OLLAMA_BASE_URL = "http://192.168.1.73:11434"
DEFAULT_OLLAMA_MODEL = "qwen3.5:9b-16k"
OLLAMA_TIMEOUT = httpx.Timeout(120.0, connect=5.0)

app = FastAPI(
    title="Agent Runtime Service",
    description="A minimal Ollama-backed chat service for the Agentic Enterprise Lab",
    version="0.1.0",
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


OllamaClient = Annotated[httpx.AsyncClient, Depends(get_ollama_client)]


@app.get("/health")
def health_check() -> dict:
    """Health check endpoint."""
    return {"status": "healthy"}


@app.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    client: OllamaClient,
) -> ChatResponse:
    """Generate a response using the configured Ollama model."""
    base_url = os.getenv("OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL).rstrip("/")
    model = os.getenv("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL)

    try:
        upstream = await client.post(
            f"{base_url}/api/generate",
            json={"model": model, "prompt": request.message, "stream": False},
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

    response = payload.get("response") if isinstance(payload, dict) else None
    if not isinstance(response, str):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Ollama returned an invalid response",
        )

    return ChatResponse(response=response)
