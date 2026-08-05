"""C2-D：Knowledge 混合检索与 Memory 语义召回的真实路由闭环。"""

import hashlib
import logging

import pytest
from sqlalchemy import delete, func, select

from app.ai.config import get_chat_model, get_vector_recall_service
from app.ai.infra.vector_recall import VectorRecallService
from app.db.session import AsyncSessionLocal
from app.main import app
from conftest import clear_overrides_keep_auth  # noqa: E402
from app.models import Document, KnowledgeChunk, LongTermMemory


class _DeterministicEmbedder:
    async def aembed_query(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode()).digest()
        return [digest[index % len(digest)] / 255.0 + 0.01 for index in range(1024)]


class _InvalidEmbedder:
    async def aembed_query(self, _text: str) -> list[float]:
        return [0.1] * 10


class _RewriteModel:
    mode = "ok"

    async def ainvoke(self, _prompt, **_kwargs):
        if self.mode == "failed":
            raise TimeoutError("private upstream detail")

        class _Response:
            content = '["缓存穿透 布隆过滤器","Redis 缓存穿透","缓存空值"]'

        return _Response()


@pytest.fixture
async def c2d_context(setup_db):
    model = _RewriteModel()
    recall = VectorRecallService(_DeterministicEmbedder())
    app.dependency_overrides[get_chat_model] = lambda: model
    app.dependency_overrides[get_vector_recall_service] = lambda: recall
    try:
        yield {"model": model, "recall": recall}
    finally:
        clear_overrides_keep_auth()
        async with AsyncSessionLocal() as session:
            await session.execute(
                delete(Document).where(Document.project_name.like("c2d-%"))
            )
            await session.execute(
                delete(LongTermMemory).where(LongTermMemory.content.like("C2-D %"))
            )
            await session.commit()


async def test_knowledge_text_file_search_and_cascade_closure(client, c2d_context):
    text_upload = await client.post(
        "/api/knowledge/upload",
        json={
            "title": "C2-D 缓存知识",
            "content": (
                "# Redis 缓存\n\n"
                "## 缓存穿透\n\n布隆过滤器与缓存空值可以拦截不存在的键。\n\n"
                "## 缓存击穿\n\n互斥锁和逻辑过期可保护热点键。"
            ),
            "source_type": "MANUAL",
            "project_name": "c2d-knowledge",
        },
    )
    file_upload = await client.post(
        "/api/knowledge/upload-file",
        files={
            "file": (
                "c2d-notes.md",
                b"# PostgreSQL\n\npgvector supports cosine search.",
                "text/markdown",
            )
        },
        data={"project_name": "c2d-knowledge"},
    )
    assert text_upload.status_code == file_upload.status_code == 200
    text_id = text_upload.json()["data"]["id"]

    search = await client.post(
        "/api/knowledge/search",
        json={"query": "缓存穿透 布隆过滤器", "top_k": 5},
    )
    assert search.status_code == 200
    hits = search.json()["data"]
    assert any(hit["document_id"] == text_id for hit in hits)
    assert all(hit["match_type"] in {"vector", "keyword", "both"} for hit in hits)
    assert any(hit["match_type"] == "both" for hit in hits)

    async with AsyncSessionLocal() as session:
        document = await session.get(Document, text_id)
        assert document is not None
        assert document.content.count("布隆过滤器") == 1
        chunk_count = await session.scalar(
            select(func.count())
            .select_from(KnowledgeChunk)
            .where(KnowledgeChunk.document_id == text_id)
        )
        assert chunk_count and chunk_count >= 2

    deleted = await client.delete(f"/api/knowledge/{text_id}")
    assert deleted.status_code == 200
    async with AsyncSessionLocal() as session:
        # ADR-0013 软删：documents 行保留（status=DELETED），chunks 物理删
        soft_deleted = await session.get(Document, text_id)
        assert soft_deleted is not None
        assert soft_deleted.status == "DELETED"
        assert (
            await session.scalar(
                select(func.count())
                .select_from(KnowledgeChunk)
                .where(KnowledgeChunk.document_id == text_id)
            )
            == 0
        )
    missing = await client.delete(f"/api/knowledge/{text_id}")
    assert missing.status_code == 404
    assert missing.json()["msg"] == "KNOWLEDGE_DOCUMENT_NOT_FOUND"


async def test_query_rewrite_failure_degrades_to_original_query(
    client,
    c2d_context,
    caplog,
):
    uploaded = await client.post(
        "/api/knowledge/upload",
        json={
            "title": "C2-D rewrite fallback",
            "content": "# 降级\n\n原查询降级后仍可检索布隆过滤器。",
            "source_type": "MANUAL",
            "project_name": "c2d-rewrite",
        },
    )
    c2d_context["model"].mode = "failed"
    with caplog.at_level(
        logging.WARNING,
        logger="app.ai.rag.query_rewriter",
    ):
        response = await client.post(
            "/api/knowledge/search",
            json={"query": "布隆过滤器", "top_k": 3},
        )
    assert response.status_code == 200
    assert any(
        hit["document_id"] == uploaded.json()["data"]["id"]
        for hit in response.json()["data"]
    )
    assert "QUERY_REWRITE_FAILED" in caplog.text
    assert "private upstream detail" not in caplog.text


@pytest.mark.parametrize(
    "payload",
    [
        {"query": "   ", "top_k": 5},
        {"query": "valid", "top_k": 0},
        {"query": "valid", "top_k": 21},
    ],
)
async def test_knowledge_search_bounds_use_stable_errors(client, c2d_context, payload):
    response = await client.post("/api/knowledge/search", json=payload)
    assert response.status_code == 422
    assert response.json()["msg"] == "KNOWLEDGE_REQUEST_INVALID"


async def test_knowledge_embedding_failure_leaves_no_document(client, c2d_context):
    app.dependency_overrides[get_vector_recall_service] = lambda: VectorRecallService(
        _InvalidEmbedder()
    )
    response = await client.post(
        "/api/knowledge/upload",
        json={
            "title": "C2-D invalid embedding",
            "content": "不会写入数据库",
            "source_type": "MANUAL",
            "project_name": "c2d-invalid-embedding",
        },
    )
    assert response.status_code == 502
    assert response.json()["msg"] == "KNOWLEDGE_EMBEDDING_FAILED"
    async with AsyncSessionLocal() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(Document)
            .where(Document.project_name == "c2d-invalid-embedding")
        )
        assert count == 0


async def test_memory_save_recall_delete_and_empty_result(client, c2d_context):
    saved = await client.post(
        "/api/memory/long-term",
        json={
            "content": "C2-D 团队使用 SQLAlchemy 2.0 async ORM",
            "memory_type": "REFERENCE",
            "metadata": {"source": "manual"},
        },
    )
    assert saved.status_code == 200
    memory_id = saved.json()["data"]["id"]

    recalled = await client.get(
        "/api/memory/long-term/search",
        params={"query": "C2-D 团队使用 SQLAlchemy 2.0 async ORM", "threshold": 0.999, "top_k": 5},
    )
    assert recalled.status_code == 200
    hit = next(item for item in recalled.json()["data"] if item["id"] == memory_id)
    assert hit["memory_type"] == "REFERENCE"
    assert hit["source"] == "manual"
    assert hit["similarity"] > 0.999

    deleted = await client.delete(f"/api/memory/long-term/{memory_id}")
    assert deleted.status_code == 200
    empty = await client.get(
        "/api/memory/long-term/search",
        params={"query": "C2-D 团队使用 SQLAlchemy 2.0 async ORM", "threshold": 0.999, "top_k": 5},
    )
    assert empty.status_code == 200
    assert all(item["id"] != memory_id for item in empty.json()["data"])
    missing = await client.delete(f"/api/memory/long-term/{memory_id}")
    assert missing.status_code == 404
    assert missing.json()["msg"] == "MEMORY_NOT_FOUND"


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        (
            "post",
            "/api/memory/long-term",
            {"content": "C2-D invalid type", "memory_type": "FACT"},
        ),
        (
            "post",
            "/api/memory/long-term",
            {"content": "x" * 4_001, "memory_type": "REFERENCE"},
        ),
        (
            "get",
            "/api/memory/long-term/search",
            {"query": "x", "threshold": 1.1, "top_k": 5},
        ),
        (
            "get",
            "/api/memory/long-term/search",
            {"query": "x", "threshold": 0.3, "top_k": 21},
        ),
    ],
)
async def test_memory_bounds_use_stable_errors(
    client,
    c2d_context,
    method,
    path,
    payload,
):
    if method == "post":
        response = await client.post(path, json=payload)
    else:
        response = await client.get(path, params=payload)
    assert response.status_code == 422
    assert response.json()["msg"] == "MEMORY_REQUEST_INVALID"


async def test_memory_embedding_and_conversation_failures_are_stable(client, c2d_context):
    missing_conversation = await client.post(
        "/api/memory/long-term",
        json={
            "content": "C2-D missing conversation",
            "memory_type": "REFERENCE",
            "conversation_id": "does-not-exist",
        },
    )
    assert missing_conversation.status_code == 404
    assert missing_conversation.json()["msg"] == "MEMORY_CONVERSATION_NOT_FOUND"

    app.dependency_overrides[get_vector_recall_service] = lambda: VectorRecallService(
        _InvalidEmbedder()
    )
    failed_embedding = await client.post(
        "/api/memory/long-term",
        json={
            "content": "C2-D invalid memory embedding",
            "memory_type": "REFERENCE",
        },
    )
    assert failed_embedding.status_code == 502
    assert failed_embedding.json()["msg"] == "MEMORY_EMBEDDING_FAILED"
    async with AsyncSessionLocal() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(LongTermMemory)
            .where(LongTermMemory.content == "C2-D invalid memory embedding")
        )
        assert count == 0


async def test_c2d_demo_knowledge_memory_closure(client, c2d_context):
    document = await client.post(
        "/api/knowledge/upload",
        json={
            "title": "C2-D demo",
            "content": "# RAG\n\npg_trgm keyword leg plus pgvector semantic leg.",
            "source_type": "MANUAL",
            "project_name": "c2d-demo",
        },
    )
    knowledge_hits = await client.post(
        "/api/knowledge/search",
        json={"query": "pgvector semantic leg", "top_k": 3},
    )
    memory = await client.post(
        "/api/memory/long-term",
        json={
            "content": "C2-D demo uses pgvector",
            "memory_type": "REFERENCE",
        },
    )
    memory_hits = await client.get(
        "/api/memory/long-term/search",
        params={"query": "C2-D demo uses pgvector", "threshold": 0.99, "top_k": 3},
    )
    assert all(
        response.status_code == 200
        for response in (document, knowledge_hits, memory, memory_hits)
    )
    print(
        "C2-D demo:",
        {
            "document_id": document.json()["data"]["id"],
            "knowledge_match_types": sorted(
                {hit["match_type"] for hit in knowledge_hits.json()["data"]}
            ),
            "memory_id": memory.json()["data"]["id"],
            "memory_recalled": any(
                hit["id"] == memory.json()["data"]["id"]
                for hit in memory_hits.json()["data"]
            ),
        },
    )
