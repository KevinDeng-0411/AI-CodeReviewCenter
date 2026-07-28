"""pytest 公共 fixtures。

PG_DB=ai_center_test 必须在导入 app.* 之前设置，使 settings 指向测试库。
集成测试用 Base.metadata.create_all 建表（验证模型）；test_migration 单独经子进程
在 ai_center_migtest 上验证 alembic up/down。
"""

import hashlib
import os

os.environ.setdefault("PG_DB", "ai_center_test")

import httpx
import pytest
from httpx import ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

import app.models  # noqa: F401  # 注册模型
from app.ai.infra.vector_recall import VectorRecallService
from app.db.base import Base
from app.db.session import AsyncSessionLocal, engine
from app.main import app


class FakeEmbedder:
    """确定性 1024 维 embedder：同文本同向量（sim≈1），不同文本近正交（sim≈0）。"""

    async def aembed_query(self, text: str) -> list[float]:
        h = hashlib.sha256(text.encode()).digest()
        # 全正向分量 -> 任意两向量 cosine 相似度 ∈ [0,1]，避免被默认 threshold 0.0 误过滤
        return [h[i % 32] / 255.0 + 0.01 for i in range(1024)]


class FakeLLM:
    async def ainvoke(self, prompt, **kw):
        class _R:
            content = "pong"

        return _R()


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
def mock_embedder() -> FakeEmbedder:
    return FakeEmbedder()


@pytest.fixture
def mock_llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def vector_recall(mock_embedder) -> VectorRecallService:
    """注入 FakeEmbedder 的 VectorRecallService（CI 友好，不打真实 Ollama）。"""
    return VectorRecallService(mock_embedder)


@pytest.fixture
async def client():
    """ASGI 测试客户端，不打真实端口。"""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
