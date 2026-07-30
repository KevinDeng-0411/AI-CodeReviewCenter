"""ShortTermMemoryManager - 工作记忆（ADR-0003）。

C1-A：PG 是消息/摘要真相源，Redis 只做可丢弃缓存。
- persist_message：PG 写（coordinator 拥有事务，显式 commit）
- refresh_message_cache / refresh_summary_cache：仅在对应 PG commit 后刷新 Redis，失败由调用方转 warning
- summarize_text：纯 LLM 调用，不持有 DB 事务（读/写由 coordinator 在短事务内完成）
- get_messages：Redis 优先，miss 回查 PG 重建（ADR-0003 fallback）
"""

from dataclasses import dataclass

import redis.asyncio as redis
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import Conversation, Message

SEP = ":::"
WINDOW_SIZE = settings.mem_window_size  # 20
SUMMARY_THRESHOLD = settings.mem_summary_threshold  # 10
TTL_SECONDS = 168 * 3600  # 7 天


@dataclass
class MessageEntry:
    role: str
    content: str


class ShortTermMemoryManager:
    def __init__(
        self,
        redis_client: redis.Redis,
        session: AsyncSession,
        chat_model=None,
    ) -> None:
        self.redis = redis_client
        self.session = session
        self.chat_model = chat_model  # 摘要用；None 则不生成摘要

    # ---------- 消息：PG 真相源 + Redis 缓存（post-commit） ----------

    async def persist_message(self, cid: str, role: str, content: str) -> Message:
        """PG 写消息（add + flush）。coordinator 负责显式 commit。"""
        msg = Message(
            conversation_id=cid, role=role, content=content, token_count=len(content) // 2
        )
        self.session.add(msg)
        await self.session.flush()
        return msg

    async def refresh_message_cache(self, cid: str, role: str, content: str) -> None:
        """PG commit 后刷新 Redis 滑窗（post-commit）。失败抛出，由调用方转 warning。"""
        key = f"msgs:{cid}"
        await self.redis.rpush(key, f"{role}{SEP}{content}")
        await self.redis.ltrim(key, -WINDOW_SIZE, -1)
        await self.redis.expire(key, TTL_SECONDS)

    async def get_messages(self, cid: str) -> list[MessageEntry]:
        try:
            messages = await self.read_cached_messages(cid)
        except Exception:
            messages = []
        if not messages:  # ADR-0003 fallback：Redis miss -> 回查 PG 重建
            messages = await self.read_recent_messages(cid)
            if messages:
                try:
                    await self.refill_message_cache(cid, messages)
                except Exception:
                    pass
        return messages

    async def read_cached_messages(self, cid: str) -> list[MessageEntry]:
        """仅访问 Redis，不读数据库；故障由调用方决定 warning/fallback 语义。"""
        entries = await self.redis.lrange(f"msgs:{cid}", 0, -1)
        return [self._parse(e) for e in entries]

    async def read_recent_messages(self, cid: str) -> list[MessageEntry]:
        """仅访问 PG，读取最近窗口；不访问 Redis。"""
        entries = await self._recent_from_pg(cid)
        return [self._parse(e) for e in entries]

    async def refill_message_cache(self, cid: str, messages: list[MessageEntry]) -> None:
        """仅访问 Redis，用 PG 读取结果重建滑窗。"""
        entries = [f"{message.role}{SEP}{message.content}" for message in messages]
        await self._refill_redis(cid, entries)

    async def get_context_window(self, cid: str) -> str:
        parts = []
        summary = await self.get_summary(cid)
        if summary:
            parts.append(f"## 历史对话摘要\n{summary}")
        msgs = await self.get_messages(cid)
        if msgs:
            parts.append("## 最近对话\n" + "\n".join(f"{m.role}: {m.content}" for m in msgs))
        return "\n\n".join(parts)

    async def message_count(self, cid: str) -> int:
        """PG 消息总数（不受 Redis 滑窗裁剪影响，用于摘要阈值）。"""
        from sqlalchemy import func

        return (
            await self.session.scalar(
                select(func.count()).select_from(Message).where(Message.conversation_id == cid)
            )
            or 0
        )

    # ---------- 摘要：PG 真相 + Redis 缓存 ----------

    async def get_summary(self, cid: str) -> str | None:
        s = await self.read_cached_summary(cid)
        if s:  # Redis 缓存优先
            return s
        # miss -> PG conversations.summary（不重算）
        s = await self.read_summary_from_pg(cid)
        if s:
            await self.refresh_summary_cache(cid, s)  # 回填缓存
        return s

    async def read_cached_summary(self, cid: str) -> str | None:
        """仅访问 Redis，不读数据库。"""
        return await self.redis.get(f"summary:{cid}")

    async def read_summary_from_pg(self, cid: str) -> str | None:
        """仅访问 PG，不访问 Redis。"""
        return await self.session.scalar(
            select(Conversation.summary).where(Conversation.conversation_id == cid)
        )

    async def summarize_text(self, messages: list[MessageEntry], existing: str | None) -> str | None:
        """纯 LLM 摘要（不持有 DB 事务）。返回 None 表示无需生成。"""
        if self.chat_model is None or not messages:
            return None
        half = max(1, len(messages) // 2)
        to_summarize = messages[:half]
        conv = "\n".join(f"{m.role}: {m.content}" for m in to_summarize)
        prompt = (
            f"请将以下对话历史总结为简洁摘要(200字以内),保留关键信息:\n{conv}\n\n"
            f"现有摘要(如有):{existing or '无'}\n\n请合并新旧信息输出最终摘要:"
        )
        resp = await self.chat_model.ainvoke(prompt)
        return resp.content if hasattr(resp, "content") else str(resp)

    async def write_summary(self, cid: str, text: str) -> None:
        """PG 写摘要（coordinator commit）。与 summary_message_count 同事务（C1-B）。"""
        await self.session.execute(
            update(Conversation).where(Conversation.conversation_id == cid).values(summary=text)
        )
        await self.session.flush()

    async def refresh_summary_cache(self, cid: str, text: str) -> None:
        """PG commit 后刷新 Redis 摘要缓存（post-commit）。"""
        key = f"summary:{cid}"
        # 先失效旧值再写新值：若 SET 失败，后续读取会回查 PG，而不会继续命中
        # 已落后于 PostgreSQL 真相的旧摘要。
        await self.redis.delete(key)
        await self.redis.set(key, text, ex=TTL_SECONDS)

    async def clear(self, cid: str) -> None:
        """清除会话短期记忆（Redis 缓存）。"""
        await self.redis.delete(f"msgs:{cid}", f"summary:{cid}")

    # ---------- PG 读取辅助 ----------

    async def _recent_from_pg(self, cid: str) -> list[str]:
        r = await self.session.execute(
            select(Message)
            .where(Message.conversation_id == cid)
            .order_by(Message.id.desc())
            .limit(WINDOW_SIZE)
        )
        return [f"{m.role}{SEP}{m.content}" for m in reversed(r.scalars().all())]

    async def _refill_redis(self, cid: str, entries: list[str]) -> None:
        key = f"msgs:{cid}"
        # PG fallback 必须精确替换缓存；若之前 lrange 故障但 key 实际存在，盲 append
        # 会制造重复/伪完整窗口。
        await self.redis.delete(key)
        if not entries:
            return
        await self.redis.rpush(key, *entries)
        await self.redis.ltrim(key, -WINDOW_SIZE, -1)
        await self.redis.expire(key, TTL_SECONDS)

    @staticmethod
    def _parse(entry: str) -> MessageEntry:
        idx = entry.find(SEP)
        if idx > 0:
            return MessageEntry(entry[:idx], entry[idx + len(SEP):])
        return MessageEntry("", entry)
