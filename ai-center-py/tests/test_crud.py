"""P1：基础 CRUD + 父子级联（ADR-0002 文档-分块、ADR-0004 会话-消息）。"""

import pytest
from sqlalchemy import select

from app.models import Conversation, Document, KnowledgeChunk, Message
from app.repositories import Repository


@pytest.fixture
def repo(db_session):
    def _f(model):
        return Repository(db_session, model)

    return _f


async def test_document_chunk_cascade_delete(db_session):
    doc = Document(title="Redis 最佳实践", source_type="MANUAL", project_name="ai-center", content="全文...")
    db_session.add(doc)
    await db_session.flush()
    for i in range(3):
        db_session.add(
            KnowledgeChunk(document_id=doc.id, chunk_index=i, chunk_content=f"chunk-{i}")
        )
    await db_session.flush()

    chunks = (
        await db_session.execute(
            select(KnowledgeChunk).where(KnowledgeChunk.document_id == doc.id)
        )
    ).scalars().all()
    assert len(chunks) == 3

    await db_session.delete(doc)  # passive_deletes -> DB CASCADE 删 chunks
    await db_session.flush()

    leftover = (
        await db_session.execute(
            select(KnowledgeChunk).where(KnowledgeChunk.document_id == doc.id)
        )
    ).scalars().all()
    assert leftover == []


async def test_conversation_message_cascade_delete(db_session):
    conv = Conversation(conversation_id="conv-abc", title="你好")
    db_session.add(conv)
    await db_session.flush()
    db_session.add(Message(conversation_id="conv-abc", role="USER", content="hi"))
    db_session.add(Message(conversation_id="conv-abc", role="ASSISTANT", content="hello"))
    await db_session.flush()

    msgs = (
        await db_session.execute(
            select(Message).where(Message.conversation_id == "conv-abc")
        )
    ).scalars().all()
    assert len(msgs) == 2

    await db_session.delete(conv)
    await db_session.flush()

    leftover = (
        await db_session.execute(
            select(Message).where(Message.conversation_id == "conv-abc")
        )
    ).scalars().all()
    assert leftover == []


async def test_repository_get_and_list(repo):
    doc_repo = repo(Document)
    d = await doc_repo.add(
        Document(title="t1", source_type="DOC", project_name="p", content="c1")
    )
    assert d.id is not None
    got = await doc_repo.get(d.id)
    assert got is not None and got.title == "t1"
    docs = await doc_repo.list(limit=10)
    assert any(x.id == d.id for x in docs)
