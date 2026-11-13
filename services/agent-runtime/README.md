# Agent Runtime Service

A minimal Python FastAPI service providing health check endpoints for the Agentic Enterprise Lab.

## Local Development

```bash
# Start with uvicorn (development mode)
uvicorn app.main:app --host 0.0.0.0 --port 8000

# Or run tests and then the server
pytest && uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Build & Run Locally

```bash
docker build -f Dockerfile.multi-stage -t agent-runtime:local .
docker run --rm -p 8000:8000 agent-runtime:local
```

## CI Pipeline

The repository includes a GitHub Actions workflow that automatically:
1. Runs tests on push to `main`
2. Builds and publishes the Docker image to GHCR with an immutable tag based on commit SHA

### Required Secrets

Configure the following in your GitHub repository settings:
- `GITHUB_TOKEN`: Automatically provided for container registry access

## API Endpoints

| Endpoint  | Method | Description           |
|-----------|--------|-----------------------|
| `/health` | GET    | Health check endpoint |
