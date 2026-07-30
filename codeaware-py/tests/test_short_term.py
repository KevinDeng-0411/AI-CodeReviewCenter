"""P3-2 / C1-A：短期记忆 - 滑窗 / PG fallback / 摘要双写（ADR-0003）。mock LLM。

C1-A：save_message 拆为 persist_message(PG) + refresh_message_cache(Redis post-commit)。
"""

from app.models import Conversation


async def _ensure_conv(db_session, cid):
    db_session.add(Conversation(conversation_id=cid, title="t"))
    await db_session.flush()


async def _save(short_term, cid, role, content):
    """PG 先 persist、后刷 Redis（模拟 coordinator 的 PG-commit-then-cache-refresh）。"""
    await short_term.persist_message(cid, role, content)
    await short_term.refresh_message_cache(cid, role, content)


async def test_sliding_window_trims(short_term, db_session):
    cid = "conv-window"
    await _ensure_conv(db_session, cid)
    for i in range(25):  # > WINDOW_SIZE(20)
        await _save(short_term, cid, "USER" if i % 2 == 0 else "ASSISTANT", f"msg{i}")
    msgs = await short_term.get_messages(cid)
    assert len(msgs) == 20  # 裁剪到窗口
    assert msgs[-1].content == "msg24"
    assert msgs[0].content == "msg5"


async def test_pg_fallback_when_redis_miss(short_term, redis_client, db_session):
    cid = "conv-fallback"
    await _ensure_conv(db_session, cid)
    await _save(short_term, cid, "USER", "hello")
    await _save(short_term, cid, "ASSISTANT", "hi")
    await redis_client.delete(f"msgs:{cid}")  # 清 Redis -> 强制 PG fallback
    msgs = await short_term.get_messages(cid)
    assert len(msgs) == 2  # 从 PG 重建
    assert msgs[0].content == "hello"
    assert msgs[1].content == "hi"
    assert await redis_client.llen(f"msgs:{cid}") == 2  # 回填 Redis


async def test_summary_double_write_redis_and_pg(short_term, redis_client, db_session):
    cid = "conv-summary"
    await _ensure_conv(db_session, cid)
    for i in range(12):  # >= SUMMARY_THRESHOLD(10)
        await _save(short_term, cid, "USER" if i % 2 == 0 else "ASSISTANT", f"m{i}")
    msgs = await short_term.get_messages(cid)
    existing = await short_term.get_summary(cid)
    summary_text = await short_term.summarize_text(msgs, existing)  # FakeLLM -> "pong"
    await short_term.write_summary(cid, summary_text)
    await short_term.refresh_summary_cache(cid, summary_text)

    assert await short_term.get_summary(cid) == "pong"  # Redis
    await redis_client.delete(f"summary:{cid}")  # 清 Redis -> 从 PG 读
    assert await short_term.get_summary(cid) == "pong"  # PG conversations.summary


async def test_clear(short_term, redis_client, db_session):
    cid = "conv-clear"
    await _ensure_conv(db_session, cid)
    await _save(short_term, cid, "USER", "x")
    assert await redis_client.llen(f"msgs:{cid}") == 1
    await short_term.clear(cid)
    assert await redis_client.llen(f"msgs:{cid}") == 0
