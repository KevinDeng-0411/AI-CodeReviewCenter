"""ShortTermMemoryManager - 工作记忆（ADR-0003）。

C1-B：PG 是消息/摘要真相源，Redis 只做可丢弃缓存。
- persist_message：PG 写（coordinator 拥有事务，显式 commit）
- refresh_message_cache / refresh_summary_cache：仅在对应 PG commit 后刷新 Redis，失败由调用方转 warning
- read_summary_work / conditional_write_summary：短事务读取增量、按旧水位线原子提交
- generate_summary：纯 LLM 调用，不持有 DB 事务
- get_messages：Redis 优先，miss 回查 PG 重建（ADR-0003 fallback）
"""

from dataclasses import dataclass

import redis.asyncio as redis
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import Conversation, Message

SEP = ":::"
WINDOW_SIZE = settings.mem_window_size  # 20
TTL_SECONDS = 168 * 3600  # 7 天
MIDDLE_TRUNCATION = "\n…[中间内容已截断]…\n"
TAIL_TRUNCATION = "…[内容已截断]"


@dataclass
class MessageEntry:
    role: str
    content: str


@dataclass(frozen=True)
class SummaryWork:
    existing_summary: str | None
    expected_watermark: int
    total_count: int
    messages: tuple[MessageEntry, ...]


@dataclass(frozen=True)
class SummaryPrompt:
    text: str
    included_message_count: int


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

    async def read_summary_work(
        self,
        cid: str,
        *,
        threshold: int,
        interval: int,
        batch_size: int,
    ) -> SummaryWork | None:
        """从 PG 读取一次摘要决策快照；调用方须在 session 退出后再调用 LLM。"""
        state = (
            await self.session.execute(
                select(Conversation.summary, Conversation.summary_message_count).where(
                    Conversation.conversation_id == cid
                )
            )
        ).one_or_none()
        if state is None:
            return None
        existing_summary, watermark = state
        total_count = await self.message_count(cid)
        if total_count < threshold or total_count - watermark < interval:
            return None

        result = await self.session.execute(
            select(Message.role, Message.content)
            .where(Message.conversation_id == cid)
            .order_by(Message.id.asc())
            .offset(watermark)
            .limit(batch_size)
        )
        messages = tuple(MessageEntry(role=row.role, content=row.content) for row in result)
        if not messages:
            return None
        return SummaryWork(
            existing_summary=existing_summary,
            expected_watermark=watermark,
            total_count=total_count,
            messages=messages,
        )

    @staticmethod
    def build_summary_prompt(
        work: SummaryWork,
        *,
        max_chars: int,
    ) -> SummaryPrompt | None:
        """构造有界增量摘要 Prompt，并返回实际纳入的消息数。"""
        instruction = (
            "请将既有摘要与新增对话合并为简洁摘要（200字以内），"
            "保留用户目标、关键事实、决定与未完成事项。\n\n"
        )
        summary_header = "## 既有摘要\n"
        messages_header = "\n\n## 新增对话\n"
        suffix = "\n\n只输出合并后的最终摘要。"

        existing = work.existing_summary or "（无）"
        summary_limit = min(2000, max_chars // 4)
        existing = ShortTermMemoryManager._truncate_middle(existing, summary_limit)
        prompt = instruction + summary_header + existing + messages_header

        included = 0
        for message in work.messages:
            separator = "" if included == 0 else "\n"
            prefix = f"{message.role}: "
            full_line = separator + prefix + message.content
            available = max_chars - len(prompt) - len(suffix)
            if len(full_line) <= available:
                prompt += full_line
                included += 1
                continue

            content_budget = available - len(separator) - len(prefix)
            if content_budget < len(TAIL_TRUNCATION):
                break
            prompt += (
                separator
                + prefix
                + ShortTermMemoryManager._truncate_tail(message.content, content_budget)
            )
            included += 1
            break

        if included == 0:
            return None
        return SummaryPrompt(
            text=(prompt + suffix)[:max_chars],
            included_message_count=included,
        )

    async def generate_summary(self, prompt: str) -> str | None:
        """纯 LLM 调用；调用方保证此时没有打开的数据库事务。"""
        if self.chat_model is None:
            return None
        response = await self.chat_model.ainvoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        content = content.strip()
        return content or None

    async def conditional_write_summary(
        self,
        cid: str,
        text: str,
        *,
        expected_watermark: int,
        target_watermark: int,
    ) -> bool:
        """按旧水位线条件更新摘要与新水位线，防止旧结果覆盖并发赢家。"""
        result = await self.session.execute(
            update(Conversation)
            .where(
                Conversation.conversation_id == cid,
                Conversation.summary_message_count == expected_watermark,
            )
            .values(
                summary=text,
                summary_message_count=target_watermark,
            )
        )
        return result.rowcount == 1

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
    def _truncate_middle(text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        if limit <= len(MIDDLE_TRUNCATION):
            return MIDDLE_TRUNCATION[:limit]
        remaining = limit - len(MIDDLE_TRUNCATION)
        head = (remaining + 1) // 2
        tail = remaining // 2
        return text[:head] + MIDDLE_TRUNCATION + (text[-tail:] if tail else "")

    @staticmethod
    def _truncate_tail(text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        if limit <= len(TAIL_TRUNCATION):
            return TAIL_TRUNCATION[:limit]
        return text[: limit - len(TAIL_TRUNCATION)] + TAIL_TRUNCATION

    @staticmethod
    def _parse(entry: str) -> MessageEntry:
        idx = entry.find(SEP)
        if idx > 0:
            return MessageEntry(entry[:idx], entry[idx + len(SEP):])
        return MessageEntry("", entry)
