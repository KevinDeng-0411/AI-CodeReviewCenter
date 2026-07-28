"""P0：BusinessException 全局兜底 -> 400 + Result 结构。

通过临时挂载一个抛 BusinessException 的路由验证主 app 的异常处理器注册。
"""

import httpx

from app.core.exceptions import BusinessException
from app.main import app


async def test_business_exception_handler(client: httpx.AsyncClient):
    async def _raise():
        raise BusinessException("测试业务异常")

    app.add_api_route("/_test/biz", _raise, methods=["GET"])
    try:
        r = await client.get("/_test/biz")
        assert r.status_code == 400
        body = r.json()
        assert body["code"] == 0
        assert body["msg"] == "测试业务异常"
        assert body["data"] is None
    finally:
        app.router.routes = [rt for rt in app.router.routes if getattr(rt, "path", None) != "/_test/biz"]


async def test_business_exception_custom_code(client: httpx.AsyncClient):
    async def _raise():
        raise BusinessException("未授权", code=401)

    app.add_api_route("/_test/biz2", _raise, methods=["GET"])
    try:
        r = await client.get("/_test/biz2")
        assert r.status_code == 400  # HTTP 状态固定 400，业务 code 透传
        assert r.json()["code"] == 401
    finally:
        app.router.routes = [rt for rt in app.router.routes if getattr(rt, "path", None) != "/_test/biz2"]
