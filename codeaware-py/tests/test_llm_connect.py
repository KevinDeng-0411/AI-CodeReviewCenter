"""P2：LLM 连通性（mock 接线 + 单例）。"""

from langchain_openai import ChatOpenAI

from app.ai.config import get_chat_model, get_embedding_model
from app.main import app


async def test_get_chat_model_singleton(monkeypatch):
    # ChatOpenAI 新版构造即校验凭据，注入 dummy key（不实际调用）
    from app.core.config import settings

    monkeypatch.setattr(settings, "llm_api_key", "sk-dummy")
    get_chat_model.cache_clear()
    try:
        m1 = get_chat_model()
        m2 = get_chat_model()
        assert isinstance(m1, ChatOpenAI)
        assert m1 is m2  # lru_cache 单例
    finally:
        get_chat_model.cache_clear()


async def test_ai_health_endpoint_mocked(client, setup_db, mock_llm, mock_embedder):
    """连通性端点接线：mock LLM/Embedder，验证三通结构。"""
    app.dependency_overrides[get_chat_model] = lambda: mock_llm
    app.dependency_overrides[get_embedding_model] = lambda: mock_embedder
    try:
        r = await client.get("/api/ai/health")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["llm"] is True
        assert data["embedding"] is True
        assert data["dim"] == 1024
        assert data["pgvector"] is True
    finally:
        app.dependency_overrides.clear()
