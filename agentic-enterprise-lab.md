# Agentic Enterprise Lab

A minimal, scalable foundation for building enterprise-grade AI agents without external AI framework dependencies. This project demonstrates best practices for containerized Python services with robust CI/CD pipelines.

## 🎯 Vision

Build an **enterprise-ready infrastructure** for intelligent agents using proven patterns:
- ✅ No external AI frameworks yet (pure Python)
- ✅ FastAPI + uvicorn for lightweight services
- ✅ Pytest-based testing strategy
- ✅ Immutable Docker images with SHA tags
- ✅ GitHub Actions CI/CD automation

## 🏗️ Architecture Overview

```
agentic-enterprise-lab/
├── .agents-architecture/          # Architecture documentation
├── services/                      # Agent runtime services
│   └── agent-runtime/            # Minimal FastAPI health service
├── github/                        # CI/CD workflows
│   └── workflows/                # GitHub Actions pipelines
├── docs/                          # Project documentation
└── README.md                      # Original placeholder (keep this)
```

## 🚀 Quick Start

### For Developers

See [docs/LOCAL_DEVELOPMENT.md](docs/LOCAL_DEVELOPMENT.md) for complete setup instructions.

```bash
# Clone and set up
git clone https://github.com/your-org/agentic-enterprise-lab.git
cd agentic-enterprise-lab

# Navigate to service
cd services/agent-runtime

# Install dependencies
uv pip install .[dev]

# Run tests
pytest

# Start server (separate terminal)
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### For Operations/DevOps

See [.agents-architecture/README.md](.agents-architecture/README.md) for architecture details and deployment strategies.

```bash
# Build locally with SHA tag
COMMIT_SHA=$(git rev-parse --short HEAD)
docker build -t agent-runtime:local --build-arg BUILD_COMMIT="${COMMIT_SHA}" .

# Run container
docker run -p 8000:8000 agent-runtime:local

# Test health endpoint
curl http://localhost:8000/health
```

## 📚 Documentation

| Document | Description | Audience |
|----------|-------------|----------|
| [docs/LOCAL_DEVELOPMENT.md](docs/LOCAL_DEVELOPMENT.md) | Complete local setup guide, testing, and development workflows | Developers |
| [.agents-architecture/README.md](.agents-architecture/README.md) | Architecture decisions, monorepo structure, CI/CD pipeline details | DevOps, Architects, Developers |

## 🧪 Testing Strategy

```bash
# Run all tests
pytest -v --tb=short

# With coverage report
pytest --cov=. --cov-report=term-missing

# Watch mode (if configured)
pytest --reuse-process
```

All tests must pass before CI will succeed. This ensures quality gates are met.

## 🔧 Local Development Commands

### Install Dependencies
```bash
cd services/agent-runtime
uv pip install .[dev]  # or: pip install -e ".[dev]"
```

### Run Tests
```bash
pytest -v --tb=short
```

### Lint Code
```bash
ruff check app tests
```

### Start Service
```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### Test Endpoint
```bash
curl http://localhost:8000/health
# Expected: {"status": "healthy"}
```

## 🐳 Docker Build

```bash
cd services/agent-runtime

# Build locally (for testing)
COMMIT_SHA=$(git rev-parse --short HEAD)
docker build -t agent-runtime:local \
  --build-arg BUILD_COMMIT="${COMMIT_SHA}" .

# Run container
docker run -p 8000:8000 agent-runtime:local

# With health check and logging
docker run -d --name test-agent \
  -p 8000:8000 \
  --log-driver json-file \
  agent-runtime:local
```

## 🔄 CI/CD Pipeline (GitHub Actions)

The `github/workflows/ci.yaml` file defines the automated pipeline:

**Triggers:**
- ✅ Push to `main` branch
- ✅ Pull requests targeting `main`
- ✅ Tags matching `v*.*`

**Automated Steps:**
1. Checkout code with LFS support
2. Set up Python 3.12 environment
3. Install dependencies (including dev)
4. Run pytest suite with verbose output
5. Lint check with ruff (main branch only)
6. Build Docker image tagged with commit SHA: `sha-${COMMIT_SHA}`
7. Push to GitHub Container Registry (GHCR)

**Security:**
- Minimal container base image (Python 3.12-slim-base)
- Non-root user (UID 100000+) for containers
- Read-only filesystem where possible
- No privileged mode
- Immutable tags prevent drift

## 📋 Key Files

| File | Purpose |
|------|---------|
| `services/agent-runtime/app/main.py` | FastAPI application code |
| `services/agent-runtime/tests/test_health.py` | Pytest test suite |
| `services/agent-runtime/Dockerfile` | Docker build configuration |
| `services/agent-runtime/pyproject.toml` | Python project metadata + dependencies |
| `.github/workflows/ci.yaml` | GitHub Actions CI/CD pipeline |
| `.gitignore` | Git ignore patterns for the monorepo |

## 🔒 Security Best Practices

1. **Immutable Containers**: Images tagged with commit SHA ensure reproducibility
2. **Non-root Execution**: Containers run as non-root user (UID 100000+)
3. **Minimal Base Image**: Python 3.12-slim-base reduces attack surface
4. **No Privileged Mode**: Never use `--privileged` flag in production
5. **Read-Only Filesystem**: Where possible, bind mounts are read-only

## 🎓 Learning Resources

If you're new to these tools:
- [FastAPI Documentation](https://fastapi.tiangolo.com/) - Modern web framework
- [Pytest Tutorial](https://docs.pytest.org/en/stable/getting-started.html) - Testing framework
- [Docker Fundamentals](https://www.docker.com/products/docker-desktop) - Containerization
- [GitHub Actions Basics](https://docs.github.com/en/actions) - CI/CD automation

## 🤝 Contributing

This is a template project. When contributing:
1. **Follow architecture principles** (single responsibility, immutable tags)
2. **Test before pushing** (pytest must pass locally and on CI)
3. **Keep dependencies minimal** (add only what's needed)
4. **Document your changes** (update relevant README files)

## 📝 License

This project is a template for learning and experimentation. Use as appropriate for your needs.

---

<div align="center">
<strong>Start with docs/LOCAL_DEVELOPMENT.md or .agents-architecture/README.md</strong>
</div>