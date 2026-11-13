FROM python:3.12-slim-trixie@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b AS builder

WORKDIR /build

COPY pyproject.toml requirements.lock README.md ./
COPY app ./app
RUN pip wheel --no-cache-dir --constraint requirements.lock --wheel-dir /wheels .

FROM python:3.12-slim-trixie@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY --from=builder /wheels /wheels
RUN apt-get update && \
    apt-get install --only-upgrade --yes --no-install-recommends zlib1g && \
    rm -rf /var/lib/apt/lists/* && \
    pip install --no-cache-dir /wheels/* && \
    python -m pip uninstall --yes pip setuptools && \
    rm -rf /wheels && \
    groupadd --system app && \
    useradd --system --gid app --no-create-home app

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
