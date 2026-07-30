"""pytest 公共 fixtures。

连接信息（PG/Redis）由 scripts/run_tests_safe.py 注入；不再 setdefault 固定库名。
任何 destructive 操作（drop_all / flushdb）前经 _safeguard.assert_safe_targets()
二次校验：目标必须属于本次一次性 stack（含 stack_id 后缀、不在开发库黑名单）。
集成测试用 Base.metadata.create_all 建表；test_migration 在 stack_id mig 库上验证 up/down。
"""

import hashlib
import os

# 行为标记（非 DB 目标）：main.py 据此跳过前端静态挂载。PG/Redis 目标由 runner 注入，不在此 setdefault。
os.environ.setdefault("CODEAWARE_TESTING", "1")

import httpx
import pytest
from httpx import ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

import app.models  # noqa: F401  # 注册模型
from app.ai.infra.vector_recall import VectorRecallService
from app.db.base import Base
from app.core.config import settings
from app.db.session import AsyncSessionLocal, engine
from app.main import app
import redis.asyncio as aioredis

from _safeguard import assert_safe_targets  # fail-closed 目标守卫


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
    """会话级：建扩展 + 建表；会话结束 drop。destructive 前先 fail-closed 校验目标。"""
    assert_safe_targets()  # 拒绝开发库/未授权裸跑
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
async def redis_client():
    """测试用 Redis。fixture 内创建以绑定 session loop，每测试 flush 隔离；flush 前校验目标。"""
    assert_safe_targets()
    client = aioredis.from_url(settings.redis_url, decode_responses=True)
    await client.flushdb()
    yield client
    await client.flushdb()
    await client.aclose()


@pytest.fixture
async def short_term(redis_client, db_session, mock_llm):
    from app.ai.memory.short_term import ShortTermMemoryManager
    return ShortTermMemoryManager(redis_client, db_session, mock_llm)


@pytest.fixture
async def long_term(db_session, vector_recall):
    from app.ai.memory.long_term import LongTermMemoryManager
    return LongTermMemoryManager(db_session, vector_recall)


@pytest.fixture
def chunker():
    from app.ai.rag.semantic_chunker import SemanticChunker
    return SemanticChunker()


@pytest.fixture
async def hybrid_retriever(db_session, vector_recall):
    from app.ai.rag.hybrid_retriever import HybridRetriever
    return HybridRetriever(db_session, vector_recall)


@pytest.fixture
async def rag_service(db_session, chunker, vector_recall, mock_llm):
    from app.ai.rag.query_rewriter import QueryRewriter
    from app.ai.rag.hybrid_retriever import HybridRetriever
    from app.ai.services.rag import RagService
    return RagService(
        db_session, chunker, vector_recall,
        QueryRewriter(mock_llm), HybridRetriever(db_session, vector_recall),
    )


@pytest.fixture
async def chat_service(db_session, mock_llm, short_term, long_term, rag_service):
    from app.ai.prompt.template_manager import PromptTemplateManager
    from app.ai.services.chat import ChatService
    return ChatService(
        db_session, mock_llm, short_term, long_term,
        rag_service, PromptTemplateManager(db_session),
    )


@pytest.fixture
async def client():
    """ASGI 测试客户端，不打真实端口。"""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
