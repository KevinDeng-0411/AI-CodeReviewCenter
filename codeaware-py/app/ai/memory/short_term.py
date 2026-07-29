"""ShortTermMemoryManager - 工作记忆（ADR-0003）。

PG(messages) 真相源 + Redis(滑窗+摘要) 缓存 + miss 回查 PG 重建；
LLM 摘要 PG conversations.summary(真相)+Redis(缓存)，miss 读 PG 不重算，写入异步双写。
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

    # ---------- 消息（PG 真相源 + Redis 缓存 + fallback）----------
    async def save_message(self, cid: str, role: str, content: str, bg=None) -> None:
        key = f"msgs:{cid}"
        await self.redis.rpush(key, f"{role}{SEP}{content}")
        await self.redis.ltrim(key, -WINDOW_SIZE, -1)  # 裁剪滑窗
        await self.redis.expire(key, TTL_SECONDS)

        size = await self.redis.llen(key)
        if size >= SUMMARY_THRESHOLD and size % 5 == 0 and bg is not None and self.chat_model:
            bg.add_task(self.generate_summary, cid)  # 真异步（Java 版实为同步）

        await self._persist_message(cid, role, content)  # 真相源写 PG

    async def get_messages(self, cid: str) -> list[MessageEntry]:
        key = f"msgs:{cid}"
        entries = await self.redis.lrange(key, 0, -1)
        if not entries:  # ADR-0003 fallback：Redis miss -> 回查 PG 重建
            entries = await self._recent_from_pg(cid)
            if entries:
                await self._refill_redis(cid, entries)
        return [self._parse(e) for e in entries]

    async def get_context_window(self, cid: str) -> str:
        parts = []
        summary = await self.get_summary(cid)
        if summary:
            parts.append(f"## 历史对话摘要\n{summary}")
        msgs = await self.get_messages(cid)
        if msgs:
            parts.append("## 最近对话\n" + "\n".join(f"{m.role}: {m.content}" for m in msgs))
        return "\n\n".join(parts)

    # ---------- 摘要（ADR-0003 决策点 4）----------
    async def get_summary(self, cid: str) -> str | None:
        skey = f"summary:{cid}"
        s = await self.redis.get(skey)
        if s:  # Redis 缓存优先
            return s
        # miss -> PG conversations.summary（不重算）
        s = await self.session.scalar(
            select(Conversation.summary).where(Conversation.conversation_id == cid)
        )
        if s:
            await self.redis.set(skey, s, ex=TTL_SECONDS)  # 回填缓存
        return s

    async def generate_summary(self, cid: str) -> None:
        """异步生成/更新摘要并双写 Redis + PG。

        生产环境由 BackgroundTask 调用；此处 flush（不 commit），调用方负责事务提交，
        保证可测试性（测试 rollback 即可隔离）。
        """
        if self.chat_model is None:
            return
        msgs = await self.get_messages(cid)
        if not msgs:
            return
        half = max(1, len(msgs) // 2)
        to_summarize = msgs[:half]
        conv = "\n".join(f"{m.role}: {m.content}" for m in to_summarize)
        existing = await self.get_summary(cid)
        prompt = (
            f"请将以下对话历史总结为简洁摘要(200字以内),保留关键信息:\n{conv}\n\n"
            f"现有摘要(如有):{existing or '无'}\n\n请合并新旧信息输出最终摘要:"
        )
        resp = await self.chat_model.ainvoke(prompt)
        text = resp.content if hasattr(resp, "content") else str(resp)
        # 双写：Redis 缓存 + PG 真相
        await self.redis.set(f"summary:{cid}", text, ex=TTL_SECONDS)
        await self.session.execute(
            update(Conversation).where(Conversation.conversation_id == cid).values(summary=text)
        )
        await self.session.flush()

    async def clear(self, cid: str) -> None:
        """清除会话短期记忆（Redis 缓存）。"""
        await self.redis.delete(f"msgs:{cid}", f"summary:{cid}")

    # ---------- PG 持久化 ----------
    async def _persist_message(self, cid: str, role: str, content: str) -> None:
        self.session.add(
            Message(conversation_id=cid, role=role, content=content, token_count=len(content) // 2)
        )
        await self.session.flush()

    async def _recent_from_pg(self, cid: str) -> list[str]:
        r = await self.session.execute(
            select(Message).where(Message.conversation_id == cid).order_by(Message.id.desc()).limit(WINDOW_SIZE)
        )
        return [f"{m.role}{SEP}{m.content}" for m in reversed(r.scalars().all())]

    async def _refill_redis(self, cid: str, entries: list[str]) -> None:
        key = f"msgs:{cid}"
        await self.redis.rpush(key, *entries)
        await self.redis.ltrim(key, -WINDOW_SIZE, -1)
        await self.redis.expire(key, TTL_SECONDS)

    @staticmethod
    def _parse(entry: str) -> MessageEntry:
        idx = entry.find(SEP)
        if idx > 0:
            return MessageEntry(entry[:idx], entry[idx + len(SEP):])
        return MessageEntry("", entry)
