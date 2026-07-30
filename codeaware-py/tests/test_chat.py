"""C1-A：TurnCoordinator - typed SSE 事件 / 时序 / 失败 / 并发 / USER 一次。"""

import asyncio
import json
import logging

import pytest
from sqlalchemy import select

from app.ai.rag.query_rewriter import QueryRewriter
from app.ai.services.turn_coordinator import (
    ChatTurnInProgress,
    TurnCoordinator,
)
from app.api.v1.chat import _ClosingStreamingResponse, _format_sse
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


class _AbortAwareLLM(_StreamLLM):
    """可在给定 token 后阻塞，并记录上游是否把取消传进 astream。"""

    def __init__(self, tokens=()):
        super().__init__(tokens)
        self.waiting = asyncio.Event()
        self.release = asyncio.Event()
        self.abort_observed = False
        self.closed = False

    async def astream(self, prompt, **kw):
        self.captured_prompt = prompt
        try:
            for token in self.tokens:
                class _C:
                    content = token

                yield _C()
            self.waiting.set()
            await self.release.wait()
        except (asyncio.CancelledError, GeneratorExit):
            self.abort_observed = True
            raise
        finally:
            self.closed = True


class _CloseFailingStream:
    def __init__(self):
        self._sent = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._sent:
            raise StopAsyncIteration
        self._sent = True

        class _C:
            content = "ok"

        return _C()

    async def aclose(self):
        raise RuntimeError("sensitive provider close details")


class _CloseFailingLLM(_StreamLLM):
    def __init__(self):
        super().__init__([])

    def astream(self, prompt, **kw):
        self.captured_prompt = prompt
        return _CloseFailingStream()


def _coord(redis_client, vector_recall, chunker, llm):
    return TurnCoordinator(llm, redis_client, vector_recall, chunker, QueryRewriter(llm))


async def _events(coord, cid, message):
    coord.acquire_turn(cid)
    return [ev async for ev in coord.run(cid, message)]


def _frame_payload(frame: str) -> dict:
    data_line = next(line for line in frame.splitlines() if line.startswith("data: "))
    return json.loads(data_line.removeprefix("data: "))


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
    cid = evs[0].conversation_id
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
    cid = evs[0].conversation_id
    # USER 保留、ASSISTANT 未持久化
    msgs = (await db_session.execute(
        select(Message).where(Message.conversation_id == cid)
    )).scalars().all()
    assert [m.role for m in msgs] == ["USER"]


async def test_concurrent_same_cid_returns_409(redis_client, vector_recall, chunker):
    coord = _coord(redis_client, vector_recall, chunker, _StreamLLM(["a"]))
    cid = "conv-concurrent"
    coord.acquire_turn(cid)
    try:
        with pytest.raises(ChatTurnInProgress):
            coord.acquire_turn(cid)
    finally:
        coord._release(cid)


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
    coord.acquire_turn(cid)
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
    assert isinstance(evs[0], ChatStarted)
    # USER/ASSISTANT 缓存刷新失败 -> context/post_turn warning(message_cache)
    assert any(isinstance(e, PostTurnWarning) and e.component == "message_cache" for e in evs)
    # PG 真相仍存在（无孤儿问题：PG 有，Redis 无）
    msgs = (await db_session.execute(
        select(Message).where(Message.conversation_id == cid).order_by(Message.id)
    )).scalars().all()
    assert [m.role for m in msgs] == ["USER", "ASSISTANT"]
    # 核心结果仍完成
    assert isinstance(evs[-1], ChatCompleted)


async def test_abort_before_first_token_closes_model_and_releases_new_cid_guard(
    db_session, redis_client, vector_recall, chunker, caplog
):
    llm = _AbortAwareLLM()
    coord = _coord(redis_client, vector_recall, chunker, llm)
    event_gen = coord.run(None, "首 token 前取消的敏感问题")
    stream = _format_sse(event_gen)

    started = _frame_payload(await anext(stream))
    cid = started["conversation_id"]
    assert cid in TurnCoordinator._active

    pending_frame = asyncio.create_task(anext(stream))
    await asyncio.wait_for(llm.waiting.wait(), timeout=2)
    with caplog.at_level(logging.INFO, logger="app.ai.services.turn_coordinator"):
        pending_frame.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending_frame

    assert llm.abort_observed is True
    assert llm.closed is True
    assert cid not in TurnCoordinator._active
    assert "client_disconnected" in caplog.text
    assert "首 token 前取消的敏感问题" not in caplog.text

    msgs = (await db_session.execute(
        select(Message).where(Message.conversation_id == cid).order_by(Message.id)
    )).scalars().all()
    assert [(m.role, m.content) for m in msgs] == [("USER", "首 token 前取消的敏感问题")]


async def test_abort_after_multiple_tokens_discards_partial_and_releases_guard(
    db_session, redis_client, vector_recall, chunker, caplog
):
    llm = _AbortAwareLLM(["partial", " answer"])
    coord = _coord(redis_client, vector_recall, chunker, llm)
    event_gen = coord.run(None, "多个 token 后取消的敏感问题")
    response = _ClosingStreamingResponse(
        _format_sse(event_gen),
        event_gen=event_gen,
        on_close=lambda: coord.release_turn(None),
    )
    body_payloads: list[dict] = []

    async def interrupted_send(message):
        if message["type"] != "http.response.body" or not message.get("body"):
            return
        body_payloads.append(_frame_payload(message["body"].decode()))
        if len(body_payloads) == 3:
            raise OSError("client socket closed")

    with caplog.at_level(logging.INFO, logger="app.ai.services.turn_coordinator"):
        with pytest.raises(OSError, match="client socket closed"):
            await response.stream_response(interrupted_send)

    cid = body_payloads[0]["conversation_id"]
    assert body_payloads[1]["delta"] + body_payloads[2]["delta"] == "partial answer"
    assert llm.abort_observed is True
    assert llm.closed is True
    assert cid not in TurnCoordinator._active
    assert "client_disconnected" in caplog.text
    assert "多个 token 后取消的敏感问题" not in caplog.text

    msgs = (await db_session.execute(
        select(Message).where(Message.conversation_id == cid).order_by(Message.id)
    )).scalars().all()
    assert [(m.role, m.content) for m in msgs] == [("USER", "多个 token 后取消的敏感问题")]


async def test_response_start_failure_releases_existing_cid_guard(
    redis_client, vector_recall, chunker
):
    coord = _coord(redis_client, vector_recall, chunker, _AbortAwareLLM())
    cid = "response-start-failure"
    coord.acquire_turn(cid)
    event_gen = coord.run(cid, "不会进入 generator")
    response = _ClosingStreamingResponse(
        _format_sse(event_gen),
        event_gen=event_gen,
        on_close=lambda: coord.release_turn(cid),
    )

    async def fail_before_body(_message):
        raise OSError("response start failed")

    with pytest.raises(OSError, match="response start failed"):
        await response.stream_response(fail_before_body)

    assert cid not in TurnCoordinator._active


async def test_model_stream_close_failure_is_sanitized_and_does_not_override_completion(
    redis_client, vector_recall, chunker, caplog
):
    coord = _coord(redis_client, vector_recall, chunker, _CloseFailingLLM())

    with caplog.at_level(logging.WARNING, logger="app.ai.services.turn_coordinator"):
        evs = await _events(coord, None, "close failure question")

    assert isinstance(evs[-1], ChatCompleted)
    assert "model_stream_close_failed" in caplog.text
    assert "sensitive provider close details" not in caplog.text


async def test_completed_frame_send_failure_is_recorded_as_disconnect(
    redis_client, vector_recall, chunker, caplog
):
    coord = _coord(redis_client, vector_recall, chunker, _StreamLLM(["complete"]))
    event_gen = coord.run(None, "terminal send failure")
    response = _ClosingStreamingResponse(
        _format_sse(event_gen),
        event_gen=event_gen,
        on_close=lambda: coord.release_turn(None),
    )
    cid = ""

    async def fail_on_completed(message):
        nonlocal cid
        if message["type"] != "http.response.body" or not message.get("body"):
            return
        payload = _frame_payload(message["body"].decode())
        cid = payload["conversation_id"]
        if "assistant_message_id" in payload:
            raise OSError("terminal send failed")

    with caplog.at_level(logging.INFO, logger="app.ai.services.turn_coordinator"):
        with pytest.raises(OSError, match="terminal send failed"):
            await response.stream_response(fail_on_completed)

    assert cid not in TurnCoordinator._active
    assert "client_disconnected" in caplog.text
