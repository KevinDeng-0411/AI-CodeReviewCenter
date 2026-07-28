"""pytest 公共 fixtures。

PG_DB=ai_center_test 必须在导入 app.* 之前设置，使 settings 指向测试库。
集成测试用 Base.metadata.create_all 建表（验证模型）；test_migration 单独经子进程
在 ai_center_migtest 上验证 alembic up/down。
"""

import os

os.environ.setdefault("PG_DB", "ai_center_test")

import httpx
import pytest
from httpx import ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

import app.models  # noqa: F401  # 注册模型
from app.db.base import Base
from app.db.session import AsyncSessionLocal, engine
from app.main import app


@pytest.fixture(scope="session")
async def setup_db():
    """会话级：建扩展 + 建表；会话结束 drop。"""
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def db_session(setup_db) -> AsyncSession:
    """每测试一个 session，结束 rollback 隔离。"""
    async with AsyncSessionLocal() as session:
        yield session
        await session.rollback()


@pytest.fixture
async def client():
    """ASGI 测试客户端，不打真实端口。"""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
