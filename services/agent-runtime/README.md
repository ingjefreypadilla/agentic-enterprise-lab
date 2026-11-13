# Agent Runtime

A minimal FastAPI service exposing `GET /health`.

From this directory:

```bash
python -m pip install --constraint requirements.lock --editable '.[dev]'
ruff check app tests
pytest --cov=app
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Build the container with `docker build --tag agent-runtime:local .`.
