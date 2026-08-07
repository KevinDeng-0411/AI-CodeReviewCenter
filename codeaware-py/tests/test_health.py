"""C1-D：liveness/readiness 健康检查。"""

import httpx

from app.api.v1 import system_health


async def test_health_returns_200(client: httpx.AsyncClient):
    r = await client.get("/health")
    assert r.status_code == 200


async def test_health_envelope(client: httpx.AsyncClient):
    body = r.json() if (r := await client.get("/health")) else {}
    assert body["code"] == 1
    assert body["msg"] == "success"
    assert body["data"] == {"status": "up"}


async def test_health_live_is_compatible_liveness(client: httpx.AsyncClient):
    r = await client.get("/health/live")
    assert r.status_code == 200
    assert r.json()["data"] == {"status": "up"}


async def test_health_ready_when_all_dependencies_up(client: httpx.AsyncClient, monkeypatch):
    async def up():
        return None

    monkeypatch.setattr(system_health, "_check_postgres", up)
    monkeypatch.setattr(system_health, "_check_redis", up)
    monkeypatch.setattr(system_health, "_check_ollama", up)
    monkeypatch.setattr(system_health, "_check_deepseek", up)

    r = await client.get("/health/ready")
    assert r.status_code == 200
    assert r.json()["data"] == {
        "status": "ready",
        "checks": {"postgres": "up", "redis": "up", "ollama": "up", "deepseek": "up"},
    }


async def test_health_ready_sanitizes_dependency_failure(
    client: httpx.AsyncClient, monkeypatch
):
    async def up():
        return None

    async def redis_down():
        raise RuntimeError("redis://user:secret@development.internal/0")

    monkeypatch.setattr(system_health, "_check_postgres", up)
    monkeypatch.setattr(system_health, "_check_redis", redis_down)
    monkeypatch.setattr(system_health, "_check_ollama", up)
    monkeypatch.setattr(system_health, "_check_deepseek", up)

    r = await client.get("/health/ready")
    assert r.status_code == 503
    body = r.json()
    assert body == {
        "code": 0,
        "msg": "not ready",
        "data": {
            "status": "not_ready",
            "checks": {"postgres": "up", "redis": "down", "ollama": "up", "deepseek": "up"},
        },
    }
    assert "secret" not in r.text
