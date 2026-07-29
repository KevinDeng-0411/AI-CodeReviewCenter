"""P3-2：长期记忆 - 内联向量召回（ADR-0001）。mock embedder。"""


async def test_save_and_recall_order(long_term):
    await long_term.save_memory("Redis 缓存穿透", "KNOWLEDGE")
    await long_term.save_memory("Java 多线程并发", "KNOWLEDGE")
    results = await long_term.recall("Redis 缓存穿透", top_k=2)
    assert len(results) == 2
    assert results[0][0].content == "Redis 缓存穿透"  # 同文本最相似
    assert results[0][1] > results[1][1]
    assert results[0][1] > 0.99  # 自身 ~1.0


async def test_recall_threshold(long_term):
    await long_term.save_memory("A", "KNOWLEDGE")
    results = await long_term.recall("A", top_k=5, threshold=0.999)
    assert len(results) == 1


async def test_save_with_metadata_and_embedding(long_term):
    mem = await long_term.save_memory(
        "团队用 MyBatis-Plus", "KNOWLEDGE", conversation_id="c1", metadata={"src": "wiki"}
    )
    assert mem.id is not None
    assert mem.embedding is not None and len(mem.embedding) == 1024
    assert mem.meta == {"src": "wiki"}
    assert mem.conversation_id == "c1"


async def test_delete(long_term):
    mem = await long_term.save_memory("to delete", "KNOWLEDGE")
    await long_term.delete(mem.id)
    results = await long_term.recall("to delete", top_k=5)
    assert all(r[0].id != mem.id for r in results)
