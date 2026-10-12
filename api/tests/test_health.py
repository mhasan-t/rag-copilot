from httpx import AsyncClient
from redis.asyncio import Redis

from src.core.dependencies import get_redis
from src.main import app


async def test_health_reports_ok_when_dependencies_are_up(client: AsyncClient):
    response = await client.get("/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"database": "ok", "redis": "ok"}}


async def test_health_returns_uniform_503_when_a_dependency_is_down(client: AsyncClient):
    # Port 1 refuses connections, so only the Redis check fails.
    app.dependency_overrides[get_redis] = lambda: Redis.from_url("redis://localhost:1")

    response = await client.get("/v1/health")

    assert response.status_code == 503
    error = response.json()["error"]
    assert error["code"] == "service_unavailable"
    assert error["details"]["database"] == "ok"
    assert error["details"]["redis"].startswith("unavailable")


async def test_unknown_route_uses_uniform_error_shape(client: AsyncClient):
    response = await client.get("/v1/does-not-exist")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "http_error"
