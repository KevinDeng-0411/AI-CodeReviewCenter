"""P4：API 契约测试（mock LLM/embedder，非 redis 端点）。

Chat/CR 已在服务层测试（P3-1/P3-4）；此处测 Knowledge/Memory/Prompt API。
"""

import hashlib

import pytest

from app.ai.config import get_chat_model, get_vector_recall_service
from app.ai.infra.vector_recall import VectorRecallService
from app.ai.prompt.template_manager import PromptTemplateManager
from app.core.enums import PromptType
from app.db.session import get_db
from app.main import app
from conftest import clear_overrides_keep_auth  # noqa: E402


class _FakeLLM:
    async def ainvoke(self, prompt, **kw):
        class _R:
            content = "pong"

        return _R()


class _FakeEmbedder:
    async def aembed_query(self, text):
        h = hashlib.sha256(text.encode()).digest()
        return [h[i % 32] / 255.0 + 0.01 for i in range(1024)]


@pytest.fixture
def api_overrides(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_chat_model] = lambda: _FakeLLM()
    app.dependency_overrides[get_vector_recall_service] = lambda: VectorRecallService(_FakeEmbedder())
    yield
    clear_overrides_keep_auth()


async def test_knowledge_upload_and_search(client, api_overrides):
    r = await client.post(
        "/api/knowledge/upload",
        json={"title": "缓存", "content": "# 缓存\n## 穿透\n布隆过滤器方案", "source_type": "MANUAL", "project_name": "p"},
    )
    assert r.status_code == 200
    assert r.json()["data"]["id"] is not None

    r2 = await client.post("/api/knowledge/search", json={"query": "布隆过滤器方案", "top_k": 3})
    assert r2.status_code == 200
    results = r2.json()["data"]
    assert len(results) >= 1
    assert "match_type" in results[0]


async def test_memory_save_and_search(client, api_overrides):
    r = await client.post(
        "/api/memory/long-term",
        json={"content": "团队用 SQLAlchemy 2.0", "memory_type": "REFERENCE"},
    )
    assert r.status_code == 200
    assert r.json()["data"]["id"] is not None

    r2 = await client.get(
        "/api/memory/long-term/search?query=SQLAlchemy&threshold=0.0&top_k=5"
    )
    assert r2.status_code == 200
    results = r2.json()["data"]
    assert any("SQLAlchemy" in r["content"] for r in results)


async def test_prompt_list_and_activate(client, db_session, api_overrides):
    pm = PromptTemplateManager(db_session)
    tpl = await pm.save_and_activate(
        PromptType.CODE_REVIEW, name="v1", role_setting="r", template_body="{{source_code}}"
    )
    r = await client.get("/api/prompts?type=CODE_REVIEW")
    assert r.status_code == 200
    assert len(r.json()["data"]) >= 1

    r2 = await client.post(f"/api/prompts/{tpl.id}/activate")
    assert r2.status_code == 200
    assert r2.json()["data"]["is_active"] is True
