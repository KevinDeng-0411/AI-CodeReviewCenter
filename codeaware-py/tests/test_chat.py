"""C1-A：TurnCoordinator - typed SSE 事件 / 时序 / 失败 / 并发 / USER 一次。"""

import asyncio

import pytest
from sqlalchemy import select

from app.ai.rag.query_rewriter import QueryRewriter
from app.ai.services.turn_coordinator import (
    ChatTurnInProgress,
    TurnCoordinator,
)
from app.models import Message
from app.schemas.chat_events import ChatCompleted, ChatFailed, ChatStarted, PostTurnWarning, TokenDelta


class _StreamLLM:
    """支持 astream(分片) + ainvoke(摘要/抽取) 的 fake；记录捕获的 prompt。"""

    def __init__(self, tokens, ainvoke_text="pong摘要", astream_raises=False):
        self.tokens = tokens
        self.ainvoke_text = ainvoke_text
        self.astream_raises = astream_raises
        self.captured_prompt = None

    async def ainvoke(self, prompt, **kw):
        self.captured_prompt = prompt
        class _R:
            content = self.ainvoke_text
        return _R()

    async def astream(self, prompt, **kw):
        self.captured_prompt = prompt
        if self.astream_raises:
            raise RuntimeError("model boom")
        for t in self.tokens:
            class _C:
                content = t
            yield _C()


def _coord(redis_client, vector_recall, chunker, llm):
    return TurnCoordinator(llm, redis_client, vector_recall, chunker, QueryRewriter(llm))


async def _events(coord, cid, message):
    coord.acquire_turn(cid)
    return [ev async for ev in coord.run(cid, message)]


async def test_sync_returns_reply_and_persists(db_session, redis_client, vector_recall, chunker):
    coord = _coord(redis_client, vector_recall, chunker, _StreamLLM(["hel", "lo"]))
    result = await coord.run_sync(None, "你好")
    assert result.reply == "hello"
    assert result.conversation_id
    # USER + ASSISTANT 已落 PG
    msgs = (await db_session.execute(
        select(Message).where(Message.conversation_id == result.conversation_id).order_by(Message.id)
    )).scalars().all()
    assert [m.role for m in msgs] == ["USER", "ASSISTANT"]
    assert msgs[0].content == "你好"
    assert msgs[1].content == "hello"


async def test_stream_events_sequence_and_terminal(db_session, redis_client, vector_recall, chunker):
    coord = _coord(redis_client, vector_recall, chunker, _StreamLLM([" a", "b"]))
    evs = await _events(coord, None, "q")
    # 首事件 chat.started，含 cid
    assert isinstance(evs[0], ChatStarted)
    assert evs[0].created is True
    import sys; [sys.stderr.write(f"DEBUG ev type={type(e).__name__} comp={getattr(e,"component",None)}\n") for e in evs]; cid = evs[0].conversation_id
    assert cid
    # sequence 从 1 严格递增
    seqs = [e.sequence for e in evs]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs) and seqs[0] == 1
    # token.delta 保真（含前导空格）
    deltas = [e.delta for e in evs if isinstance(e, TokenDelta)]
    assert "".join(deltas) == " ab"
    # 唯一终态 chat.completed
    assert isinstance(evs[-1], ChatCompleted)
    assert sum(1 for e in evs if isinstance(e, (ChatCompleted,))) == 1


async def test_delta_preserves_newline(db_session, redis_client, vector_recall, chunker):
    coord = _coord(redis_client, vector_recall, chunker, _StreamLLM(["line1\n", "line2"]))
    evs = await _events(coord, None, "q")
    deltas = [e.delta for e in evs if isinstance(e, TokenDelta)]
    assert "".join(deltas) == "line1\nline2"


async def test_model_failure_keeps_user_no_assistant(db_session, redis_client, vector_recall, chunker):
    coord = _coord(redis_client, vector_recall, chunker, _StreamLLM(["x"], astream_raises=True))
    evs = await _events(coord, None, "你好")
    # 失败终态
    failed = [e for e in evs if isinstance(e, ChatFailed)]
    assert len(failed) == 1
    assert failed[0].phase == "model"
    assert failed[0].partial_output_persisted is False
    import sys; [sys.stderr.write(f"DEBUG ev type={type(e).__name__} comp={getattr(e,"component",None)}\n") for e in evs]; cid = evs[0].conversation_id
    # USER 保留、ASSISTANT 未持久化
    msgs = (await db_session.execute(
        select(Message).where(Message.conversation_id == cid)
    )).scalars().all()
    assert [m.role for m in msgs] == ["USER"]


async def test_concurrent_same_cid_returns_409(redis_client, vector_recall, chunker):
    coord = _coord(redis_client, vector_recall, chunker, _StreamLLM(["a"]))
    cid = "conv-concurrent"
    coord.acquire_turn(cid)  # 占用
    with pytest.raises(ChatTurnInProgress):
        coord.acquire_turn(cid)  # 第二次 -> 409


async def test_user_message_appears_once_in_prompt(db_session, redis_client, vector_recall, chunker):
    llm = _StreamLLM(["a"])
    coord = _coord(redis_client, vector_recall, chunker, llm)
    await coord.run_sync(None, "独特的用户问题XYZ")
    # 本轮 USER 只通过 user_message 进 prompt，不因 history 重复
    assert llm.captured_prompt.count("独特的用户问题XYZ") == 1


async def test_multi_turn_reuses_cid(db_session, redis_client, vector_recall, chunker):
    coord = _coord(redis_client, vector_recall, chunker, _StreamLLM(["a"]))
    r1 = await coord.run_sync(None, "第一问")
    cid = r1.conversation_id
    r2 = await coord.run_sync(cid, "第二问")
    assert r2.conversation_id == cid
    msgs = (await db_session.execute(
        select(Message).where(Message.conversation_id == cid).order_by(Message.id)
    )).scalars().all()
    assert len(msgs) == 4  # 2 轮 × 2


class _FailingRedis:
    """刷新失败但读取委托真 redis 的包装（测 post-commit 缓存降级）。"""

    def __init__(self, real):
        self._real = real

    async def rpush(self, *a, **kw):
        raise RuntimeError("redis down")

    async def set(self, *a, **kw):
        raise RuntimeError("redis down")

    def __getattr__(self, name):
        return getattr(self._real, name)


async def test_redis_refresh_failure_warns_but_pg_truth_persists(db_session, redis_client, vector_recall, chunker):
    coord = _coord(_FailingRedis(redis_client), vector_recall, chunker, _StreamLLM(["a"]))
    evs = await _events(coord, None, "问题")
    cid = evs[0].conversation_id
    # USER/ASSISTANT 缓存刷新失败 -> context/post_turn warning(message_cache)
    assert any(isinstance(e, PostTurnWarning) and e.component == "message_cache" for e in evs)
    # PG 真相仍存在（无孤儿问题：PG 有，Redis 无）
    msgs = (await db_session.execute(
        select(Message).where(Message.conversation_id == cid).order_by(Message.id)
    )).scalars().all()
    assert [m.role for m in msgs] == ["USER", "ASSISTANT"]
    # 核心结果仍完成
    assert isinstance(evs[-1], ChatCompleted)
