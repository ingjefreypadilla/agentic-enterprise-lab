# Agent Runtime

A minimal FastAPI service exposing `GET /health` and an Ollama-backed
`POST /chat` endpoint. Qwen can choose the `list_pods` tool to inspect Pods in
the fixed `agentic-lab` namespace and then summarize the Kubernetes API result.

Ollama configuration defaults to:

```text
OLLAMA_BASE_URL=http://192.168.1.73:11434
OLLAMA_MODEL=qwen3.5:9b-16k
```

Override either environment variable when needed.

## Kubernetes tool

`list_pods` is the only allowed tool. It takes no arguments, uses the Pod's
projected ServiceAccount token and cluster CA, and calls only:

```text
GET /api/v1/namespaces/agentic-lab/pods
```

The runtime rejects unknown tools and all tool arguments (including namespace
overrides), limits each chat request to three tool calls, and uses a five-second
Kubernetes API timeout. Ollama requests retain their existing 120-second
timeout. Kubernetes and Ollama error bodies are not returned to callers.

Outside Kubernetes, ordinary chat responses still work. A locally requested
`list_pods` call fails safely because no in-cluster ServiceAccount token exists.

From this directory:

```bash
python -m pip install --constraint requirements.lock --editable '.[dev]'
ruff check app tests
pytest --cov=app
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

```bash
curl --fail --request POST http://127.0.0.1:8000/chat \
  --header 'Content-Type: application/json' \
  --data '{"message":"Hello"}'
```

The request and response contracts remain `{"message":"..."}` and
`{"response":"..."}` respectively.

Build the container with `docker build --tag agent-runtime:local .`.
