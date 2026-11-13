# Agentic Enterprise Lab

A minimal FastAPI AI agent with tests, a non-root container image, and GitHub
Actions checks that publish immutable images to GitHub Container Registry
(GHCR) after pushes to `main`. The Ollama-backed agent can list Pods in the
`agentic-lab` namespace through a single allowlisted Kubernetes tool.

## Local development

Python 3.10 or newer is required. CI and the container use Python 3.12.

```bash
cd services/agent-runtime
python -m venv .venv
source .venv/bin/activate
python -m pip install --constraint requirements.lock --editable '.[dev]'
ruff check app tests
pytest --cov=app
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In another terminal:

```bash
curl --fail http://127.0.0.1:8000/health
```

The expected response is `{"status":"healthy"}`.

## Container

```bash
cd services/agent-runtime
docker build --tag agent-runtime:local .
docker run --rm --read-only --publish 127.0.0.1:8000:8000 agent-runtime:local
```

The image includes a Docker health check and runs as an unprivileged user.

See [docs/LOCAL_DEVELOPMENT.md](docs/LOCAL_DEVELOPMENT.md) for validation and
CI/GHCR details. Kubernetes manifests under `deploy/k3s` include a dedicated
ServiceAccount and a namespaced Role that grants only `list` on Pods; existing
container security settings and resource requests/limits remain in place.
