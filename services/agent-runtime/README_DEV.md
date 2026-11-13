# Agent Runtime Service - Local Development Guide

A minimal FastAPI service providing health check endpoints. No AI frameworks or external dependencies.

## Prerequisites

- Python 3.12+
- Docker 20+ (recommended)

## Quick Start

```bash
# Clone and navigate to service
cd services/agent-runtime

# Install in development mode with tests
uv pip install .[dev]  # or: pip install -e ".[dev]"

# Run tests
pytest

# Start the server (separate terminal)
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Local Development Commands

### Install Dependencies
```bash
# Using uv (recommended)
uv pip install .[dev]

# Using pip
pip install -e ".[dev]"
```

### Run Tests
```bash
# Basic test run
pytest

# With detailed output and coverage
pytest -v --tb=short --cov=.
```

### Start the Service
```bash
# Development mode with auto-reload
uvicorn app.main:app --host 0.0.0.0 --port 8000

# Production mode (no reload)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### Docker Commands
```bash
# Build locally with SHA tag
docker build -t agent-runtime:local .

# Run in container
docker run --rm -p 8000:8000 agent-runtime:local

# With health check and logs
docker run -d --name agent-test -p 8000:8000 agent-runtime:local
docker logs agent-test
docker stop agent-test && docker rm agent-test
```

### Test Health Endpoint
```bash
curl http://localhost:8000/health

# With verbose output
curl -v http://localhost:8000/health
```

## Building for Production

```bash
# Build with CI-compatible Dockerfile
docker build -t ghcr.io/your-repo/agent-runtime:sha-${COMMIT_SHA} \
  --file Dockerfile .
```

## Linting & Code Quality

```bash
# Check code style (ruff)
uv pip install ruff
ruff check app tests
```

## API Reference

| Endpoint  | Method | Description           | Response                     |
|-----------|--------|-----------------------|------------------------------|
| `/health` | GET    | Health check          | `{"status": "healthy"}`      |

## Environment Variables

None required for local development. The service uses a single port (8000) with no external dependencies.

## CI/CD Pipeline

On pushes to `main`, this pipeline automatically:
1. ✅ Runs pytest tests
2. ✅ Lints code with ruff (on main branch only)
3. ✅ Builds Docker image tagged with immutable commit SHA
4. ✅ Pushes to GHCR as `sha-${COMMIT_SHA}` and `latest`

> **Note:** Always ensure tests pass before merging. The CI will fail if any test fails or lint errors exist.

## Troubleshooting

### Issue: Port 8000 already in use
```bash
# Check what's using the port
lsof -i :8000

# Kill the process (replace PID with actual)
kill <PID>
```

### Issue: Docker build fails
```bash
# Clean previous builds
rm -rf /tmp/docker-build*

# Try again
docker build -t agent-runtime:local .
```
