import asyncio

from httpx import ASGITransport, AsyncClient, Response

from app.main import app


def test_health_check() -> None:
    """Test the health check endpoint returns healthy status."""
    async def request_health() -> Response:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get("/health")

    response = asyncio.run(request_health())

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}
