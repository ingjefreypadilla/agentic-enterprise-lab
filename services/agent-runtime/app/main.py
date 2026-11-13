from fastapi import FastAPI

app = FastAPI(
    title="Agent Runtime Service",
    description="A minimal health check service for the Agentic Enterprise Lab",
    version="0.1.0",
)


@app.get("/health")
def health_check() -> dict:
    """Health check endpoint."""
    return {"status": "healthy"}
