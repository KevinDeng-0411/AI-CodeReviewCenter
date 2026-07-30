"""P1：内联 pgvector Vector(1024) 读写 + cosine 检索（ADR-0001 改进①）。"""

import random

from sqlalchemy import select

from app.models import Document, KnowledgeChunk, LongTermMemory


def _vec(seed: int) -> list[float]:
    rng = random.Random(seed)
    return [rng.random() for _ in range(1024)]


async def test_long_term_memory_vector_recall_order(db_session):
    """相同向量应最相似（cosine 距离最小），排在最前。"""
    query_vec = _vec(1)
    db_session.add_all(
        [
            LongTermMemory(content="近", memory_type="REFERENCE", embedding=_vec(1)),
            LongTermMemory(content="远", memory_type="REFERENCE", embedding=_vec(99)),
        ]
    )
    await db_session.flush()

    stmt = (
        select(
            LongTermMemory,
            (1 - LongTermMemory.embedding.cosine_distance(query_vec)).label("sim"),
        )
        .order_by(LongTermMemory.embedding.cosine_distance(query_vec))
    )
    rows = (await db_session.execute(stmt)).all()
    assert rows[0][0].content == "近"
    assert rows[0][1] > rows[1][1]
    # 自身相似度接近 1
    assert rows[0][1] > 0.99


async def test_knowledge_chunk_vector_distance(db_session):
    doc = Document(title="t", source_type="DOC", content="c")
    db_session.add(doc)
    await db_session.flush()
    kc = KnowledgeChunk(
        document_id=doc.id, chunk_index=0, chunk_content="x", embedding=_vec(5)
    )
    db_session.add(kc)
    await db_session.flush()

    stmt = (
        select(KnowledgeChunk)
        .order_by(KnowledgeChunk.embedding.cosine_distance(_vec(5)))
        .limit(1)
    )
    got = (await db_session.execute(stmt)).scalar_one()
    assert got.id == kc.id


async def test_long_term_memory_metadata_jsonb(db_session):
    """metadata JSONB 列可读写（ADR-0006 同模式）。"""
    mem = LongTermMemory(
        content="带元数据的事实",
        memory_type="REFERENCE",
        meta={"source": "team-wiki", "tags": ["redis", "cache"]},
    )
    db_session.add(mem)
    await db_session.flush()
    await db_session.refresh(mem)
    assert mem.meta["source"] == "team-wiki"
    assert "cache" in mem.meta["tags"]
