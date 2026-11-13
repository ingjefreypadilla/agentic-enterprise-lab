# Agents Directory Structure

This directory contains the architecture documentation for the Agentic Enterprise Lab.

## Monorepo Layout

```
agentic-enterprise-lab/
├── .agents-architecture/          # Architecture documentation
│   └── README.md
├── services/                      # Agent runtime services
│   └── agent-runtime/             # Minimal FastAPI service
├── .github/                       # CI/CD workflows
│   └── workflows/
├── docs/                          # Project documentation
└── README.md
```

## Key Principles

- **Single responsibility**: Each service has one clear purpose
- **Immutable tags**: Images tagged with git commit SHA for reproducibility
- **Least privilege**: No privileged containers, minimal permissions
- **Minimal dependencies**: FastAPI and Uvicorn, with no AI framework yet
- **Test first**: All services have pytest tests before deployment
