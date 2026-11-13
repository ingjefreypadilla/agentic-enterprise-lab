# Stage 1: Builder stage
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Copy and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Stage 2: Runtime stage
FROM python:3.12-slim AS runtime

# Create non-root user for security
RUN groupadd --gid 1000 appgroup && \
    useradd --uid 1000 --gid appgroup --no-create-home --shell /bin/bash appuser

WORKDIR /app

# Copy installed dependencies from builder
COPY --from=builder /build/lib /usr/local/lib

# Set ownership to non-root user
RUN chown -R appuser:apppgroup /app && \
    chmod -R 644 /app

USER appuser

# Expose the service port (FastAPI default)
ENV PORT=8000
EXPOSE ${PORT}

# Create health check directory
RUN mkdir -p /app/health_checks && \
    chmod 755 /app/health_checks

# Run the FastAPI application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "${PORT}"]
