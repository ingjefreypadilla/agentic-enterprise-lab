# Agent Runtime

A minimal FastAPI service exposing `GET /health` and an Ollama-backed
`POST /chat` endpoint.

Ollama configuration defaults to:

```text
OLLAMA_BASE_URL=http://192.168.1.73:11434
OLLAMA_MODEL=qwen3.5:9b-16k
```

Override either environment variable when needed.

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

Build the container with `docker build --tag agent-runtime:local .`.
