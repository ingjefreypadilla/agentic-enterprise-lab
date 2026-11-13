# Local development

The repository currently contains one service at `services/agent-runtime`.
It requires Python 3.10 or newer; Python 3.12 is used by CI and Docker.

## Set up and validate

```bash
cd services/agent-runtime
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install --constraint requirements.lock --editable '.[dev]'
ruff check app tests
pytest -v --tb=short --cov=app
```

Start the API with:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Then check it from another terminal:

```bash
curl --fail --show-error http://127.0.0.1:8000/health
```

The expected response is `{"status":"healthy"}`.

The `/chat` request and response shapes are unchanged:

```bash
curl --fail --show-error --request POST http://127.0.0.1:8000/chat \
  --header 'Content-Type: application/json' \
  --data '{"message":"List the Pods and investigate errors in their logs"}'
```

Qwen decides whether to call `list_pods` and can follow it with `get_pod_logs`.
Log access requires an existing Pod name and is capped at 100 recent lines.
These tools fail safely outside a cluster because they require the projected
in-cluster ServiceAccount token. Unit tests mock Ollama turns and the Kubernetes
API, so local and CI validation do not require live services.

## Kubernetes manifests

`deploy/k3s/rbac.yaml` defines the dedicated `agent-runtime` ServiceAccount and
a Role/RoleBinding scoped to `agentic-lab` with `list` on Pods and `get` on the
`pods/log` subresource.
The Deployment keeps automatic ServiceAccount token mounting disabled and
instead mounts a short-lived projected token and the cluster CA at the standard
in-cluster path. Apply all resources through `deploy/k3s/kustomization.yaml`.

## Build and test the image

```bash
cd services/agent-runtime
docker build --tag agent-runtime:local .
docker run --rm --read-only --publish 127.0.0.1:8000:8000 agent-runtime:local
```

The image runs as an unprivileged user and contains a health check for
`/health`. Use `docker inspect` to see its health state.

## CI and GHCR

The workflow at `.github/workflows/ci.yaml` runs lint and tests for pull
requests and pushes to `main`. It builds the image for both event types, but
logs in to GHCR and pushes only after a push to `main`.

Published images use the full commit SHA:

```text
ghcr.io/<owner>/<repository>/agent-runtime:sha-<full-commit-sha>
```

GitHub supplies `GITHUB_TOKEN`; no custom registry secret is required. The
workflow grants `packages: write` only to the publishing job.
