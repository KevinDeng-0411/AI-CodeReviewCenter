"""P3-2：短期记忆 - 滑窗 / PG fallback / 摘要双写（ADR-0003）。mock LLM。"""

from app.models import Conversation


async def _ensure_conv(db_session, cid):
    db_session.add(Conversation(conversation_id=cid, title="t"))
    await db_session.flush()


async def test_sliding_window_trims(short_term, db_session):
    cid = "conv-window"
    await _ensure_conv(db_session, cid)
    for i in range(25):  # > WINDOW_SIZE(20)
        await short_term.save_message(cid, "USER" if i % 2 == 0 else "ASSISTANT", f"msg{i}")
    msgs = await short_term.get_messages(cid)
    assert len(msgs) == 20  # 裁剪到窗口
    assert msgs[-1].content == "msg24"  # 最近保留
    assert msgs[0].content == "msg5"  # msg0-4 被裁掉


async def test_pg_fallback_when_redis_miss(short_term, redis_client, db_session):
    cid = "conv-fallback"
    await _ensure_conv(db_session, cid)
    await short_term.save_message(cid, "USER", "hello")
    await short_term.save_message(cid, "ASSISTANT", "hi")
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
        await short_term.save_message(cid, "USER" if i % 2 == 0 else "ASSISTANT", f"m{i}")
    await short_term.generate_summary(cid)  # 直接调（生产由 BackgroundTask 触发）

    assert await short_term.get_summary(cid) == "pong"  # FakeLLM -> Redis

    await redis_client.delete(f"summary:{cid}")  # 清 Redis -> 从 PG 读
    assert await short_term.get_summary(cid) == "pong"  # PG conversations.summary


async def test_clear(short_term, redis_client, db_session):
    cid = "conv-clear"
    await _ensure_conv(db_session, cid)
    await short_term.save_message(cid, "USER", "x")
    assert await redis_client.llen(f"msgs:{cid}") == 1
    await short_term.clear(cid)
    assert await redis_client.llen(f"msgs:{cid}") == 0
