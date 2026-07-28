"""P0：/health 健康检查。"""

import httpx


async def test_health_returns_200(client: httpx.AsyncClient):
    r = await client.get("/health")
    assert r.status_code == 200


async def test_health_envelope(client: httpx.AsyncClient):
    body = r.json() if (r := await client.get("/health")) else {}
    assert body["code"] == 1
    assert body["msg"] == "success"
    assert body["data"] == {"status": "up"}
