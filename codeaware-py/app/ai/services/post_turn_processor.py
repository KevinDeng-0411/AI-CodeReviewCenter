"""PostTurnProcessor - Chat 后处理（摘要 + 记忆抽取 + 缓存刷新）。

从 TurnCoordinator 提取，负责：
- 增量摘要生成（水位线机制）
- 长期记忆事实抽取（Celery 异步）
- 缓存刷新
"""

import logging
import os

from app.ai.memory.short_term import ShortTermMemoryManager, MessageEntry
from app.core.config import settings
from app.db.session import AsyncSessionLocal

MEMORY_EXTRACT_THRESHOLD = 4

logger = logging.getLogger(__name__)


class PostTurnProcessor:
    def __init__(self, chat_model, redis_client, vector_recall) -> None:
        self.chat_model = chat_model
        self.redis = redis_client
        self.vector_recall = vector_recall

    # ---------- 摘要 ----------

    async def run_summary(self, cid, warnings, post_warning_callback) -> None:
        """按 PG 水位线生成增量摘要；任何降级均不阻止 turn 完成。"""
        try:
            async with AsyncSessionLocal() as s:
                st = ShortTermMemoryManager(self.redis, s, self.chat_model)
                work = await st.read_summary_work(
                    cid,
                    threshold=settings.mem_summary_threshold,
                    interval=settings.mem_summary_interval,
                    batch_size=settings.mem_summary_batch_size,
                )
        except Exception:
            warnings.append(post_warning_callback(cid, "summary", "SUMMARY_FAILED", "摘要生成降级"))
            return

        if work is None:
            return
        summary_prompt = ShortTermMemoryManager.build_summary_prompt(
            work, max_chars=settings.mem_summary_max_chars,
        )
        if summary_prompt is None:
            warnings.append(post_warning_callback(cid, "summary", "SUMMARY_FAILED", "摘要生成降级"))
            return

        try:
            summary_text = await st.generate_summary(summary_prompt.text)
        except Exception:
            summary_text = None
        if not summary_text:
            warnings.append(post_warning_callback(cid, "summary", "SUMMARY_FAILED", "摘要生成降级"))
            return

        target_watermark = work.expected_watermark + summary_prompt.included_message_count
        try:
            async with AsyncSessionLocal() as s2:
                st2 = ShortTermMemoryManager(self.redis, s2, self.chat_model)
                updated = await st2.conditional_write_summary(
                    cid, summary_text,
                    expected_watermark=work.expected_watermark,
                    target_watermark=target_watermark,
                )
                if not updated:
                    return
                await s2.commit()
        except Exception:
            warnings.append(post_warning_callback(cid, "summary", "SUMMARY_FAILED", "摘要持久化降级"))
            return

        try:
            async with AsyncSessionLocal() as cache_session:
                cm = ShortTermMemoryManager(self.redis, cache_session, self.chat_model)
                await cm.refresh_summary_cache(cid, summary_text)
        except Exception:
            warnings.append(post_warning_callback(cid, "summary_cache", "REDIS_UNAVAILABLE", "摘要缓存刷新失败"))

    # ---------- 记忆抽取 ----------

    async def run_extraction(self, cid, warnings, post_warning_callback) -> None:
        """异步抽取长期记忆（提交 Celery 任务或同步降级）。"""
        try:
            msgs, _ = await self._load_messages(cid)
            if len(msgs) < MEMORY_EXTRACT_THRESHOLD:
                return

            from app.ai.tasks.memory_extract import extract_memory_task

            if os.environ.get("CODEAWARE_TESTING") == "1":
                await self._sync_extract(cid, warnings, post_warning_callback)
                return

            extract_memory_task.delay(cid, MEMORY_EXTRACT_THRESHOLD)
        except Exception as exc:
            logger.warning("memory extraction submit failed conversation_id=%s error=%s", cid, exc)
            warnings.append(post_warning_callback(cid, "memory_extraction", "EXTRACTION_FAILED", "记忆抽取任务提交失败"))

    async def _load_messages(self, cid: str) -> tuple[list[MessageEntry], bool]:
        """Redis-first + PG fallback。"""
        cache_failed = False
        try:
            async with AsyncSessionLocal() as s:
                st = ShortTermMemoryManager(self.redis, s, self.chat_model)
                messages = await st.read_cached_messages(cid)
        except Exception:
            messages = []
            cache_failed = True
        if messages:
            return messages, cache_failed
        async with AsyncSessionLocal() as s:
            st = ShortTermMemoryManager(self.redis, s, self.chat_model)
            messages = await st.read_recent_messages(cid)
        return messages, cache_failed

    async def _sync_extract(self, cid, warnings, post_warning_callback) -> None:
        """测试环境同步降级。"""
        from app.ai.memory.long_term import LongTermMemoryManager

        async with AsyncSessionLocal() as s:
            lt = LongTermMemoryManager(s, self.vector_recall)
            has_mem = await lt.has_memories(cid)
            if has_mem:
                return
            messages = await lt.read_recent_messages(cid)
            if len(messages) < MEMORY_EXTRACT_THRESHOLD:
                return
            tuples = [(m[0], m[1]) for m in messages]
            facts = await lt.extract_facts_text(tuples, self.chat_model)
            if not facts:
                return
        async with AsyncSessionLocal() as prepare_session:
            preparer = LongTermMemoryManager(prepare_session, self.vector_recall)
            prepared = await preparer.prepare_facts(facts)
        async with AsyncSessionLocal() as s2:
            lt2 = LongTermMemoryManager(s2, self.vector_recall)
            await lt2.save_prepared_facts(cid, prepared)
            await s2.commit()