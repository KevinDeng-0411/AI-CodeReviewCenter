"""ADR-0013 文档管理：列表 + 软删状态 + replace 更新。"""

import pytest

from app.ai.config import get_chat_model, get_vector_recall_service
from app.api.v1.deps import get_db
from app.main import app
from app.models import Document, KnowledgeChunk


@pytest.fixture
def mgmt_overrides(db_session, mock_llm, vector_recall):
    """让 router 用测试 session（seed 可见）+ mock embedder/LLM。"""
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_chat_model] = lambda: mock_llm
    app.dependency_overrides[get_vector_recall_service] = lambda: vector_recall
    yield
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_chat_model, None)
    app.dependency_overrides.pop(get_vector_recall_service, None)


async def _upload(client, title: str, content: str) -> int:
    r = await client.post(
        "/api/knowledge/upload",
        json={"title": title, "content": content, "source_type": "MANUAL"},
    )
    assert r.status_code == 200
    return r.json()["data"]["id"]


async def test_list_documents_returns_uploaded_with_chunk_count(client, db_session, mgmt_overrides):
    doc1 = await _upload(client, "文档一", "# 缓存击穿\n热点Key失效方案")
    doc2 = await _upload(client, "文档二", "# 摘要生成\n增量摘要水位线机制")

    r = await client.get("/api/knowledge/documents?status=ACTIVE")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["total"] == 2
    ids = [rec["id"] for rec in data["records"]]
    assert doc1 in ids and doc2 in ids
    # chunk_count 反映每个文档实际分块数
    for rec in data["records"]:
        if rec["id"] == doc1:
            assert rec["status"] == "ACTIVE"
            assert rec["chunk_count"] >= 1
            assert rec["title"] == "文档一"


async def test_delete_soft_marks_delisted_from_active(client, db_session, mgmt_overrides):
    doc1 = await _upload(client, "删我", "# 删除\n内容")
    doc2 = await _upload(client, "留我", "# 保留\n内容")

    r = await client.delete(f"/api/knowledge/{doc1}")
    assert r.status_code == 200

    # ACTIVE 列表不含 doc1
    active = await client.get("/api/knowledge/documents?status=ACTIVE")
    active_ids = [rec["id"] for rec in active.json()["data"]["records"]]
    assert doc1 not in active_ids
    assert doc2 in active_ids

    # DELETED 列表含 doc1
    deleted = await client.get("/api/knowledge/documents?status=DELETED")
    deleted_ids = [rec["id"] for rec in deleted.json()["data"]["records"]]
    assert doc1 in deleted_ids
    assert deleted.json()["data"]["total"] == 1

    # DB 行保留但 status=DELETED，chunks 物理删
    row = await db_session.get(Document, doc1)
    assert row is not None
    assert row.status == "DELETED"
    chunk_count = (
        await db_session.execute(
            KnowledgeChunk.__table__.select().where(KnowledgeChunk.document_id == doc1)
        )
    ).scalars()
    assert len(list(chunk_count)) == 0


async def test_list_pagination(client, db_session, mgmt_overrides):
    # 用唯一 project_name 标识本测试上传的文档（跨测试累积不影响相对断言）
    await _upload(client, "分页一", "# 分页\n内容一")
    await _upload(client, "分页二", "# 分页\n内容二")

    r = await client.get("/api/knowledge/documents?status=ALL&page=1&size=1")
    assert r.status_code == 200
    data = r.json()["data"]
    # total >= 2（跨测试可能累积更多），但分页结构必须正确
    assert data["total"] >= 2
    assert len(data["records"]) == 1
    assert data["page"] == 1

    # 第二页取到的是下一批（id 降序，size=1）
    r2 = await client.get("/api/knowledge/documents?status=ALL&page=2&size=1")
    assert r2.status_code == 200
    d2 = r2.json()["data"]
    assert d2["page"] == 2
    assert len(d2["records"]) == 1
    assert d2["records"][0]["id"] != data["records"][0]["id"]


async def test_delete_missing_doc_returns_404(client, db_session, mgmt_overrides):
    r = await client.delete("/api/knowledge/99999")
    assert r.status_code == 404
    assert r.json()["msg"] == "KNOWLEDGE_DOCUMENT_NOT_FOUND"


async def test_document_detail_returns_metadata_content_and_chunks(client, db_session, mgmt_overrides):
    doc_id = await _upload(client, "详情文档", "# 第一章\n缓存击穿方案\n## 第二章\n热点Key失效")

    r = await client.get(f"/api/knowledge/{doc_id}")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["title"] == "详情文档"
    assert data["status"] == "ACTIVE"
    assert "# 第一章" in data["content"]
    assert data["chunk_count"] == len(data["chunks"])
    assert len(data["chunks"]) >= 1
    # 分块按 chunk_index 排序
    indexes = [c["chunk_index"] for c in data["chunks"]]
    assert indexes == sorted(indexes)


async def test_document_detail_visible_after_soft_delete(client, db_session, mgmt_overrides):
    """已软删文档仍可查看元数据（审计/追溯），chunks 已物理删。"""
    doc_id = await _upload(client, "审计文档", "# 审计\n内容")
    await client.delete(f"/api/knowledge/{doc_id}")

    r = await client.get(f"/api/knowledge/{doc_id}")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["status"] == "DELETED"
    assert data["chunk_count"] == 0  # chunks 已物理删
    assert data["content"]  # 全文保留


async def test_document_detail_missing_returns_404(client, db_session, mgmt_overrides):
    r = await client.get("/api/knowledge/99999")
    assert r.status_code == 404
    assert r.json()["msg"] == "KNOWLEDGE_DOCUMENT_NOT_FOUND"
