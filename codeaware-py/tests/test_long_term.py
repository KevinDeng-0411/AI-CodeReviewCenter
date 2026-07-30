"""P3-2：长期记忆 - 内联向量召回（ADR-0001）。mock embedder。"""


async def test_save_and_recall_order(long_term):
    await long_term.save_memory("Redis 缓存穿透", "REFERENCE")
    await long_term.save_memory("Java 多线程并发", "REFERENCE")
    results = await long_term.recall("Redis 缓存穿透", top_k=2)
    assert len(results) == 2
    assert results[0][0].content == "Redis 缓存穿透"  # 同文本最相似
    assert results[0][1] > results[1][1]
    assert results[0][1] > 0.99  # 自身 ~1.0


async def test_recall_threshold(long_term):
    await long_term.save_memory("A", "REFERENCE")
    results = await long_term.recall("A", top_k=5, threshold=0.999)
    assert len(results) == 1


async def test_save_with_metadata_and_embedding(long_term):
    mem = await long_term.save_memory(
        "团队用 MyBatis-Plus", "REFERENCE", conversation_id="c1", metadata={"src": "wiki"}
    )
    assert mem.id is not None
    assert mem.embedding is not None and len(mem.embedding) == 1024
    assert mem.meta == {"src": "wiki"}
    assert mem.conversation_id == "c1"


async def test_delete(long_term):
    mem = await long_term.save_memory("to delete", "REFERENCE")
    await long_term.delete(mem.id)
    results = await long_term.recall("to delete", top_k=5)
    assert all(r[0].id != mem.id for r in results)


async def test_extract_from_conversation_saves_facts(long_term, db_session):
    """对话内生记忆抽取（ADR-0001）：从对话消息抽取原子事实 -> 落库 FACT + conversation_id。"""
    from sqlalchemy import select

    from app.models import Conversation, LongTermMemory, Message
    from app.schemas.memory import ExtractedFacts

    cid = "conv-extract-test"
    db_session.add(Conversation(conversation_id=cid, title="抽取测试"))
    db_session.add_all(
        [
            Message(conversation_id=cid, role="USER", content="我们项目用 FastAPI + SQLAlchemy 2.0"),
            Message(conversation_id=cid, role="ASSISTANT", content="了解，不错的异步栈"),
            Message(conversation_id=cid, role="USER", content="部署在 Kubernetes 上"),
            Message(conversation_id=cid, role="ASSISTANT", content="好的"),
        ]
    )
    await db_session.flush()

    class _FakeExtract:
        def with_structured_output(self, schema, **kw):
            class _S:
                async def ainvoke(self, prompt, **kw):
                    return ExtractedFacts(
                        facts=["项目使用 FastAPI + SQLAlchemy 2.0 作为后端栈", "项目部署在 Kubernetes 上"]
                    )

            return _S()

    count = await long_term.extract_from_conversation(cid, _FakeExtract())
    assert count == 2

    mems = (
        (await db_session.execute(select(LongTermMemory).where(LongTermMemory.conversation_id == cid)))
        .scalars()
        .all()
    )
    assert len(mems) == 2
    assert all(m.memory_type == "FACT" for m in mems)
    assert all((m.meta or {}).get("source") == "conversation" for m in mems)
    assert all(m.embedding is not None and len(m.embedding) == 1024 for m in mems)
