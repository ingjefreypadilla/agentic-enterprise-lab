import pytest
from app.main import app


def test_health_check():
    """Test the health check endpoint returns healthy status."""
    response = app.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
