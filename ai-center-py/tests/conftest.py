"""pytest 公共 fixtures。"""

import pytest
import httpx
from httpx import ASGITransport

from app.main import app


@pytest.fixture
async def client():
    """ASGI 测试客户端，不打真实端口。"""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
