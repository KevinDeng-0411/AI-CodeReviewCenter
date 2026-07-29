"""P3-3：HybridRetriever - pg_trgm + pgvector RRF + matchType（ADR-0001/0002）。"""

from app.models import Document, KnowledgeChunk


async def _seed(db_session, vector_recall):
    doc = Document(title="缓存", source_type="MANUAL", project_name="p", content="全文")
    db_session.add(doc)
    await db_session.flush()
    await vector_recall.store(
        db_session,
        KnowledgeChunk(document_id=doc.id, chunk_index=0, chunk_content="Redis缓存穿透的解决方案是布隆过滤器"),
        "Redis缓存穿透的解决方案是布隆过滤器",
    )
    await vector_recall.store(
        db_session,
        KnowledgeChunk(document_id=doc.id, chunk_index=1, chunk_content="Java多线程volatile关键字"),
        "Java多线程volatile关键字",
    )
    return doc


async def test_hybrid_search_returns_relevant(hybrid_retriever, db_session, vector_recall):
    await _seed(db_session, vector_recall)
    results = await hybrid_retriever.search("缓存穿透", top_k=2)
    assert len(results) >= 1
    assert results[0].chunk.chunk_content.startswith("Redis缓存穿透")
    assert results[0].match_type in ("vector", "keyword", "both")


async def test_hybrid_match_type_both(hybrid_retriever, db_session, vector_recall):
    """query 是 chunk0 的近似子串 -> 关键词腿命中 + 向量腿命中 -> both。"""
    await _seed(db_session, vector_recall)
    results = await hybrid_retriever.search("缓存穿透的解决方案是布隆过滤器", top_k=2)
    top = results[0]
    assert top.chunk.chunk_content.startswith("Redis缓存穿透")
    assert top.match_type == "both"
