# Local Development Guide - Agentic Enterprise Lab

Complete guide for setting up and developing in this monorepo.

## Prerequisites

### Required Software
- **Python 3.12+** (LTS version, recommended)
- **Docker 20+** (for container development)
- **git** (version control)
- **Code editor/IDE**: VS Code, PyCharm, or any Python IDE

### Optional but Recommended
- **uv** (Python package manager) - See [https://docs.astral.sh/uv/](https://docs.astral.sh/uv/)
- **Docker Desktop** with containerd
- **Git LFS** for large file support

## Quick Start Guide

### 1. Clone and Setup

```bash
# Clone repository
git clone https://github.com/your-org/agentic-enterprise-lab.git
cd agentic-enterprise-lab

# Create virtual environment (optional but recommended)
python -m venv .venv
source .venv/bin/activate  # On Linux/Mac
# or: .venv\Scripts\activate  # On Windows

# Install all project dependencies
pip install -r requirements_dev.txt
```

### 2. Verify Installation

```bash
# Run tests
pytest

# Check linting
ruff check services/agent-runtime/app

# View API docs (if you have uvicorn running)
curl http://localhost:8000/docs
```

### 3. Start Development Server

**In one terminal:**
```bash
cd services/agent-runtime
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

**In another terminal:**
```bash
curl http://localhost:8000/health
# Expected response: {"status": "healthy"}
```

## Development Workflow

### Install Dependencies for Service

```bash
cd services/agent-runtime

# Using uv (recommended)
uv pip install .[dev]

# Using traditional pip
pip install -e ".[dev]"
```

### Run Tests

```bash
# Basic test run
pytest

# With detailed output
pytest -v --tb=short

# With code coverage
pytest --cov=. --cov-report=term-missing

# Watch mode (if pytest-watch is installed)
pytest --reuse-process
```

### Lint and Format Code

```bash
# Check for style errors
ruff check app tests

# Auto-fix common issues
ruff check app tests --fix

# Import sorting
ruff check app tests --select=I001,I002
```

### Building Docker Images Locally

```bash
cd services/agent-runtime

# Build with current SHA tag (for testing)
COMMIT_SHA=$(git rev-parse --short HEAD)
docker build -t agent-runtime:local \
  --build-arg BUILD_COMMIT="${COMMIT_SHA}" .

# Or build without tag
docker build -t agent-runtime:local .
```

### Running Container Locally

```bash
# Run container with port mapping
docker run --rm -p 8000:8000 agent-runtime:local

# Run with verbose logging and health check
docker run -d \
  --name agent-test-local \
  --log-driver json-file \
  --log-opt max-size=10m \
  --log-opt max-file=3 \
  -p 8000:8000 \
  agent-runtime:local

# Check logs
docker logs agent-test-local

# Stop and clean up
docker stop agent-test-local && docker rm agent-test-local
```

## Common Development Tasks

### Adding a New Test

```python
# In services/agent-runtime/tests/test_health.py
def test_health_returns_200(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}
```

### Adding a New Endpoint

```python
# In services/agent-runtime/app/main.py
from fastapi import APIRouter, status, HTTPException

router = APIRouter()

@router.get("/ready", status_code=status.HTTP_200_OK)
async def readiness_check() -> dict:
    return {"status": "ready"}
```

### Updating Dependencies

```bash
cd services/agent-runtime

# Update fastapi (using uv)
uv pip install --upgrade fastapi

# Run tests to ensure compatibility
pytest

# Commit changes if needed
git add app/tests
git commit -m "Updated FastAPI dependency"
```

## CI/CD Integration

### Local Testing that Matches CI

To test the exact same flow as GitHub Actions:

```bash
cd services/agent-runtime

# 1. Install all dependencies (including dev)
uv pip install .[dev]

# 2. Run tests
pytest -v --tb=short

# 3. Lint check
ruff check app tests

# 4. Build Docker image
docker build -t agent-runtime:ci-test .

# 5. Run container briefly
timeout 10s docker run --rm -p 8000:8000 agent-runtime:ci-test || true
```

### Testing the GitHub Actions Flow

```bash
# Set up a test repository (GitHub must exist)
# Update .github/workflows/ci.yaml with your repo info
# Then push to trigger CI locally:
git add .
git commit -m "Test CI flow"
git push origin main
```

## Architecture Understanding

### File Structure Overview

```
services/agent-runtime/
├── app/
│   └── main.py              # FastAPI application (single file)
├── tests/
│   └── test_health.py       # All pytest tests
├── Dockerfile               # Build configuration
├── pyproject.toml           # Python project metadata + dev dependencies
├── .gitignore               # Git ignore rules
└── README_DEV.md            # This file's location (in original repo)
```

### Key Files Explained

**`pyproject.toml`**:
- Project name and version
- Build backend (Pebble)
- Runtime dependencies: `fastapi`, `uvicorn[standard]`
- Dev dependencies (group): `pytest`, `ruff`, etc.

**`Dockerfile`**:
- Uses Python 3.12-slim-base for minimal size
- Runs as non-root user (UID 100000+)
- Single-stage build for simplicity
- Exposes port 8000, includes health check

**`app/main.py`**:
- FastAPI application with router
- Simple GET endpoint at `/health`
- Returns JSON status

**`tests/test_health.py`**:
- Pytest test class
- Tests the health endpoint
- Uses FastAPI test client

## Troubleshooting

### Issue: Port 8000 Already in Use

```bash
# Find what's using port 8000
lsof -i :8000           # Linux/Mac
netstat -an | grep 8000 # Windows

# Kill the process (replace PID)
kill <PID>
```

### Issue: Docker Build Fails

```bash
# Clean Docker cache and try again
docker build --no-cache -t agent-runtime:local .

# Or clean specific layer
docker builder prune -f
```

### Issue: Test Failures on CI but Pass Locally

**Common causes:**
1. Missing dependencies in requirements
2. Different Python version (ensure 3.12)
3. Docker platform mismatch (test with same OS as CI)

**Solution:**
```bash
# Ensure you're using Python 3.12
python --version

# Install dev dependencies explicitly
uv pip install .[dev]

# Run tests with coverage
pytest --cov=. --cov-report=xml
```

### Issue: Linter Errors on CI

```bash
# Check your linting locally
ruff check app tests

# Common fixes:
# - Remove unused imports
# - Fix type hints if using typing extensions
# - Proper async/await usage
```

## Environment Variables

Currently, the service doesn't require any environment variables. However, if you plan to expand it later:

```python
# In app/main.py (future expansion)
from fastapi import FastAPI
import os

app = FastAPI()

@app.get("/config")
async def get_config():
    return {
        "DEBUG": os.getenv("APP_DEBUG", "false"),
        "WORKERS": os.getenv("UVICORN_WORKERS", "1"),
    }
```

## Best Practices

### Testing
- ✅ Keep tests in same directory as code (`tests/`)
- ✅ Use descriptive test function names
- ✅ Test one thing per test function
- ✅ Include status codes and response bodies

### Code Style
- ✅ Follow PEP 8 style guide
- ✅ Use type hints (FastAPI enforces this)
- ✅ Keep functions small and focused
- ✅ Add docstrings for public APIs

### Docker
- ✅ Use immutable tags (SHA) for production
- ✅ Build locally first, then push
- ✅ Clean build cache regularly
- ✅ Document environment variables clearly

### Development
- ✅ Run tests before committing
- ✅ Commit changes to `.gitignore` files
- ✅ Document your development process
- ✅ Keep dependencies updated

## Resources

- **FastAPI Docs**: https://fastapi.tiangolo.com/
- **Pytest Docs**: https://docs.pytest.org/
- **Docker Docs**: https://docs.docker.com/
- **GitHub Actions**: https://docs.github.com/en/actions
- **uv Package Manager**: https://docs.astral.sh/uv/

## Next Steps for Expansion

If you plan to add AI capabilities:

1. **Create a new service** under `services/` (e.g., `agent-computation`)
2. **Add more endpoints** to agent-runtime for coordination
3. **Set up database** if state persistence needed
4. **Add integration tests** for cross-service communication
5. **Implement observability** (logging, metrics, tracing)

## Support and Help

If you encounter issues:
1. Check the troubleshooting section above
2. Review error messages carefully
3. Test locally before pushing to CI
4. Ensure all prerequisites are met

Happy developing! 🚀