"""P2：共享 VectorRecallService 存取 + 召回（ADR-0001 改进①核心）。

验证内联 pgvector 存取、纯向量召回排序、混合 RRF 融合。
"""

from app.models import Document, KnowledgeChunk, LongTermMemory


async def test_store_and_pure_vector_recall(db_session, vector_recall):
    await vector_recall.store(
        db_session,
        LongTermMemory(content="Redis 缓存穿透", memory_type="REFERENCE"),
        "Redis 缓存穿透",
    )
    await vector_recall.store(
        db_session,
        LongTermMemory(content="Java 多线程并发", memory_type="REFERENCE"),
        "Java 多线程并发",
    )

    results = await vector_recall.recall(db_session, LongTermMemory, "Redis 缓存穿透", top_k=2)
    assert len(results) == 2
    assert results[0][0].content == "Redis 缓存穿透"  # 同文本相似度最高
    assert results[0][1] > 0.99  # 自身 ~1.0
    assert results[0][1] > results[1][1]


async def test_threshold_filters(db_session, vector_recall):
    await vector_recall.store(
        db_session,
        LongTermMemory(content="A", memory_type="REFERENCE"),
        "A",
    )
    # threshold=0.999 只留几乎相同的；query "A" 与存储 "A" sim≈1 -> 保留
    results = await vector_recall.recall(
        db_session, LongTermMemory, "A", top_k=5, threshold=0.999
    )
    assert len(results) == 1
    assert results[0][0].content == "A"


async def test_hybrid_recall_knowledge_chunk(db_session, vector_recall):
    doc = Document(title="缓存最佳实践", source_type="MANUAL", project_name="p", content="全文...")
    db_session.add(doc)
    await db_session.flush()

    await vector_recall.store(
        db_session,
        KnowledgeChunk(
            document_id=doc.id,
            chunk_index=0,
            chunk_content="Redis缓存穿透的解决方案是布隆过滤器",
        ),
        "Redis缓存穿透的解决方案是布隆过滤器",
    )
    await vector_recall.store(
        db_session,
        KnowledgeChunk(
            document_id=doc.id,
            chunk_index=1,
            chunk_content="Java多线程的volatile关键字",
        ),
        "Java多线程的volatile关键字",
    )

    # hybrid：query 与 chunk0 文本重叠 -> 关键词腿(pg_trgm)命中 + 向量腿 -> RRF 融合居首
    results = await vector_recall.recall(
        db_session,
        KnowledgeChunk,
        "缓存穿透",
        top_k=2,
        hybrid=True,
        text_column="chunk_content",
    )
    assert len(results) >= 1
    assert results[0][0].chunk_content.startswith("Redis缓存穿透")
