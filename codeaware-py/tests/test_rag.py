"""P3-4：RagService - 上传分块+检索+删除（ADR-0001/0002）。mock embedder/LLM。"""

from sqlalchemy import select

from app.models import Document, KnowledgeChunk


async def test_upload_document_creates_chunks_with_embeddings(rag_service, db_session):
    doc = await rag_service.upload_document(
        "缓存最佳实践",
        "# 缓存\n## 穿透\n布隆过滤器缓存空值\n## 击穿\n互斥锁逻辑过期",
        source_type="MANUAL",
        project_name="p",
    )
    assert doc.id is not None
    assert doc.content == "缓存最佳实践" or "缓存" in doc.content  # 父表存全文
    chunks = (
        await db_session.execute(select(KnowledgeChunk).where(KnowledgeChunk.document_id == doc.id))
    ).scalars().all()
    assert len(chunks) >= 2
    assert all(c.embedding is not None for c in chunks)  # 内联向量


async def test_search_finds_relevant(rag_service, db_session):
    await rag_service.upload_document(
        "缓存",
        "# 缓存\n## 穿透\n布隆过滤器缓存空值方案\n## 击穿\n互斥锁逻辑过期方案",
        "MANUAL",
        "p",
    )
    results = await rag_service.search("布隆过滤器缓存空值", top_k=3)
    assert len(results) >= 1
    assert any("穿透" in r.chunk.chunk_content or "布隆" in r.chunk.chunk_content for r in results)


async def test_delete_document_cascades(rag_service, db_session):
    doc = await rag_service.upload_document("t", "# A\n内容一", "MANUAL", "p")
    doc_id = doc.id
    await rag_service.delete_document(doc_id)
    chunks = (
        await db_session.execute(select(KnowledgeChunk).where(KnowledgeChunk.document_id == doc_id))
    ).scalars().all()
    assert len(chunks) == 0  # CASCADE
    assert await db_session.get(Document, doc_id) is None
