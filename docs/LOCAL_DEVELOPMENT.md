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
