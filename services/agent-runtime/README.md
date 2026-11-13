# Agent Runtime

A minimal FastAPI service exposing `GET /health` and an Ollama-backed
`POST /chat` endpoint. Qwen can use `list_pods` followed by `get_pod_logs` to
investigate Pods in the fixed `agentic-lab` namespace and summarize actual
Kubernetes API results.

Ollama configuration defaults to:

```text
OLLAMA_BASE_URL=http://192.168.1.73:11434
OLLAMA_MODEL=qwen3.5:9b-16k
```

Override either environment variable when needed.

## Kubernetes tools

The allowlist contains two read-only tools. `list_pods` takes no arguments.
`get_pod_logs` requires an exact Pod name and accepts an optional `tail_lines`
from 1 through 100. Both use the Pod's projected ServiceAccount token and
cluster CA and call only:

```text
GET /api/v1/namespaces/agentic-lab/pods
GET /api/v1/namespaces/agentic-lab/pods/{pod_name}/log?tailLines={1..100}
```

Before fetching logs, the runtime refreshes the Pod list and rejects names that
do not exist in `agentic-lab`. It rejects unknown tools, namespace overrides,
invalid Pod names, and log requests over 100 lines. Each chat request is limited
to three tool calls and Kubernetes requests use a five-second timeout. Ollama
requests retain their existing 120-second timeout. Upstream error bodies are not
returned to callers.

Outside Kubernetes, ordinary chat responses still work. A locally requested
Kubernetes tool call fails safely because no in-cluster ServiceAccount token
exists.

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
