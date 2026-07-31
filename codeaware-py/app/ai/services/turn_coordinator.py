"""TurnCoordinator - C1-A/C1-B: Chat 单轮编排状态机。

同步 /api/chat/send 与流式 /api/chat/send/stream 共用本协调器。
- 自管 session 生命周期：每段事务自建 AsyncSessionLocal，显式 commit；模型流式期间不持有 DB 事务。
- PG 真相源：USER/ASSISTANT/summary 先 PG commit，再 post-commit 刷 Redis；Redis 故障转 warning。
- 产出 typed ChatEvent；流式端点格式化 SSE，同步端点 drain 收集。
- per-conversation turn guard（进程内）：同 cid 进行中返回 409。
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select

from app.ai.memory.long_term import LongTermMemoryManager
from app.ai.memory.short_term import ShortTermMemoryManager, MessageEntry
from app.ai.prompt.template_manager import PromptTemplateManager
from app.ai.rag.hybrid_retriever import HybridRetriever
from app.ai.rag.query_rewriter import QueryRewriter
from app.ai.rag.semantic_chunker import SemanticChunker
from app.ai.services.rag import RagService
from app.core.config import settings
from app.core.enums import PromptType
from app.db.session import AsyncSessionLocal
from app.models import Conversation, LongTermMemory
from app.schemas.chat_events import (
    ChatCompleted,
    ChatFailed,
    ChatStarted,
    ContextWarning,
    ErrorInfo,
    PostTurnWarning,
    TokenDelta,
)

MEMORY_EXTRACT_THRESHOLD = 4

logger = logging.getLogger(__name__)


class ChatTurnInProgress(Exception):
    def __init__(self, cid: str) -> None:
        super().__init__(f"chat turn in progress: {cid}")
        self.cid = cid


class ChatConversationNotFound(Exception):
    def __init__(self, cid: str) -> None:
        super().__init__(f"chat conversation not found: {cid}")
        self.cid = cid


class ChatTurnStartFailed(Exception):
    """Transaction A 在响应创建前失败；只向 router 暴露稳定错误类型。"""


class ChatTurnFailed(Exception):
    def __init__(self, event: ChatFailed) -> None:
        super().__init__(f"chat failed: {event.phase}")
        self.event = event


@dataclass
class TurnResult:
    conversation_id: str
    reply: str
    assistant_message_id: int
    warnings: list[dict] = field(default_factory=list)


@dataclass(frozen=True)
class PreparedTurn:
    """已完成 Transaction A、可安全创建同步或流式响应的单轮输入。"""

    conversation_id: str
    created: bool
    warnings: list[dict] = field(default_factory=list)


class TurnCoordinator:
    _active: set[str] = set()  # 类级 turn guard（local-first 单 worker）

    def __init__(self, chat_model, redis_client, vector_recall, chunker, query_rewriter, lexical_recall=None) -> None:
        self.chat_model = chat_model
        self.redis = redis_client
        self.vector_recall = vector_recall
        self.chunker = chunker
        self.query_rewriter = query_rewriter
        self.lexical_recall = lexical_recall
        self._owned_guards: set[str] = set()

    def _managers(self, session):
        st = ShortTermMemoryManager(self.redis, session, self.chat_model)
        lt = LongTermMemoryManager(session, self.vector_recall)
        hybrid = HybridRetriever(session, self.vector_recall, self.lexical_recall)
        rag = RagService(session, self.chunker, self.vector_recall, self.query_rewriter, hybrid)
        pm = PromptTemplateManager(session)
        return st, lt, rag, pm

    @staticmethod
    def _log_degradation(cid: str, phase: str, component: str, code: str) -> None:
        """只记录稳定字段；禁止异常正文、Prompt、用户消息和连接信息。"""
        logger.warning(
            "chat degraded phase=%s component=%s code=%s conversation_id=%s",
            phase,
            component,
            code,
            cid,
        )

    def _context_warning(
        self, cid: str, component: str, code: str, message: str
    ) -> tuple[str, str, str]:
        self._log_degradation(cid, "context", component, code)
        return component, code, message

    def _post_warning(
        self, cid: str, component: str, code: str, message: str
    ) -> dict:
        self._log_degradation(cid, "post_turn", component, code)
        return {"component": component, "code": code, "message": message}

    @staticmethod
    def _log_failure(
        cid: str, turn_id: str, phase: str, component: str, code: str
    ) -> None:
        logger.error(
            "chat failed phase=%s component=%s code=%s conversation_id=%s turn_id=%s",
            phase,
            component,
            code,
            cid,
            turn_id,
        )

    def _acquire(self, cid: str) -> bool:
        if cid in TurnCoordinator._active:
            return False
        TurnCoordinator._active.add(cid)
        self._owned_guards.add(cid)
        return True

    def _release(self, cid: str) -> None:
        if cid in self._owned_guards:
            self._owned_guards.discard(cid)
            TurnCoordinator._active.discard(cid)

    def acquire_turn(self, cid: str | None) -> None:
        """显式获取 turn guard；主要供内部 prepare 与生命周期边界测试使用。"""
        if cid is not None and not self._acquire(cid):
            raise ChatTurnInProgress(cid)

    def release_turn(self, cid: str | None) -> None:
        """响应在 body iterator 尚未启动时也可幂等释放已领用的 guard。"""
        if cid is not None:
            self._release(cid)

    async def prepare_turn(
        self, conversation_id: str | None, message: str
    ) -> PreparedTurn:
        """响应创建前完成 existence preflight、guard 与 Transaction A。

        成功返回时 Conversation 和 USER Message 已 commit，且所有自管 session 均已
        退出；失败使用 HTTP 前置错误语义，并幂等释放已领取的 guard。
        """
        if conversation_id is not None:
            try:
                async with AsyncSessionLocal() as session:
                    exists = await session.scalar(
                        select(Conversation.id).where(
                            Conversation.conversation_id == conversation_id
                        )
                    )
            except Exception as exc:
                logger.warning(
                    "chat turn prepare failed code=conversation_preflight_failed "
                    "conversation_id=%s",
                    conversation_id,
                )
                raise ChatTurnStartFailed from exc
            if exists is None:
                raise ChatConversationNotFound(conversation_id)
            cid = conversation_id
            created = False
        else:
            cid = uuid.uuid4().hex
            while cid in TurnCoordinator._active:
                cid = uuid.uuid4().hex
            created = True

        self.acquire_turn(cid)
        try:
            warnings = await self._txn_user(cid, message, created=created)
        except BaseException as exc:
            self.release_turn(cid)
            if isinstance(exc, asyncio.CancelledError):
                logger.info(
                    "chat turn prepare cancelled code=client_disconnected "
                    "conversation_id=%s",
                    cid,
                )
                raise
            if not isinstance(exc, Exception):
                raise
            logger.warning(
                "chat turn prepare failed code=transaction_a_failed conversation_id=%s",
                cid,
            )
            raise ChatTurnStartFailed from exc
        return PreparedTurn(conversation_id=cid, created=created, warnings=warnings)

    async def run(self, prepared: PreparedTurn, message: str):
        """产出 typed 事件；Transaction A 已由 prepare_turn 在响应创建前提交。"""
        turn_id = uuid.uuid4().hex
        seq = 0

        def nxt() -> int:
            nonlocal seq
            seq += 1
            return seq

        cid = prepared.conversation_id
        terminal_emitted = False

        try:
            yield ChatStarted(
                conversation_id=cid,
                turn_id=turn_id,
                sequence=nxt(),
                created=prepared.created,
            )

            for w in prepared.warnings:
                yield ContextWarning(
                    conversation_id=cid, turn_id=turn_id, sequence=nxt(),
                    component=w["component"], code=w["code"], message=w["message"], retryable=True,
                )

            # ---- build context (exclude current USER) ----
            prompt, ctx_warns = await self._build_context(cid, message)
            if prompt is None:
                self._log_failure(
                    cid, turn_id, "context", "prompt_context", "CONTEXT_FAILED"
                )
                yield ChatFailed(
                    conversation_id=cid, turn_id=turn_id, sequence=nxt(), phase="context",
                    error=ErrorInfo(code="CONTEXT_FAILED", message="上下文构建失败", retryable=True),
                    partial_output_persisted=False,
                )
                terminal_emitted = True
                return
            for comp, code, msg in ctx_warns:
                yield ContextWarning(
                    conversation_id=cid, turn_id=turn_id, sequence=nxt(),
                    component=comp, code=code, message=msg, retryable=True,
                )

            # ---- model stream ----
            text = ""
            model_stream = None
            try:
                model_stream = self.chat_model.astream(prompt)
                async for chunk in model_stream:
                    delta = chunk.content if hasattr(chunk, "content") else str(chunk)
                    if delta:
                        text += delta
                        yield TokenDelta(
                            conversation_id=cid, turn_id=turn_id, sequence=nxt(), delta=delta
                        )
            except asyncio.CancelledError:
                raise  # 客户端断开：丢弃 partial、保留 USER、不伪造终态
            except Exception:
                self._log_failure(
                    cid, turn_id, "model", "model", "MODEL_STREAM_FAILED"
                )
                yield ChatFailed(
                    conversation_id=cid, turn_id=turn_id, sequence=nxt(), phase="model",
                    error=ErrorInfo(code="MODEL_STREAM_FAILED", message="模型生成失败", retryable=True),
                    partial_output_persisted=False,
                )
                terminal_emitted = True
                return
            finally:
                # async-for 不保证在外层 generator 被 aclose() 时关闭内层迭代器。
                # 显式 aclose 才能把 Abort 传播到 ChatOpenAI.astream()。
                close_model_stream = (
                    getattr(model_stream, "aclose", None)
                    if model_stream is not None
                    else None
                )
                if close_model_stream is not None:
                    try:
                        await close_model_stream()
                    except Exception:
                        # 关闭失败不能覆盖既有业务终态或阻止 guard 的 finally；
                        # 只记录稳定标识，不记录 Prompt、partial 或异常正文。
                        logger.warning(
                            "model stream close failed code=model_stream_close_failed "
                            "conversation_id=%s turn_id=%s",
                            cid,
                            turn_id,
                        )

            # ---- Transaction B: persist ASSISTANT + commit ----
            assistant_id = await self._txn_assistant(cid, text)
            if assistant_id is None:
                self._log_failure(
                    cid, turn_id, "persist", "message_store", "PERSIST_FAILED"
                )
                yield ChatFailed(
                    conversation_id=cid, turn_id=turn_id, sequence=nxt(), phase="persist",
                    error=ErrorInfo(code="PERSIST_FAILED", message="回复持久化失败", retryable=True),
                    partial_output_persisted=False,
                )
                terminal_emitted = True
                return

            # ---- post-turn (cache refresh + summary + extraction) ----
            try:
                post_warns = await self._post_turn(cid, text)
            except Exception:
                self._log_failure(
                    cid, turn_id, "post_turn", "post_turn", "POST_TURN_FAILED"
                )
                yield ChatFailed(
                    conversation_id=cid,
                    turn_id=turn_id,
                    sequence=nxt(),
                    phase="post_turn",
                    error=ErrorInfo(
                        code="POST_TURN_FAILED",
                        message="回复后处理失败",
                        retryable=True,
                    ),
                    partial_output_persisted=False,
                )
                terminal_emitted = True
                return
            for w in post_warns:
                yield PostTurnWarning(
                    conversation_id=cid, turn_id=turn_id, sequence=nxt(),
                    component=w["component"], code=w["code"], message=w["message"], retryable=True,
                )

            yield ChatCompleted(
                conversation_id=cid, turn_id=turn_id, sequence=nxt(),
                assistant_message_id=assistant_id,
                warning_count=len(prepared.warnings) + len(ctx_warns) + len(post_warns),
            )
            terminal_emitted = True
        except (asyncio.CancelledError, GeneratorExit):
            if not terminal_emitted:
                # 只记录稳定标识和脱敏错误码；不记录用户消息、Prompt 或模型 partial。
                logger.info(
                    "chat stream closed code=client_disconnected conversation_id=%s turn_id=%s",
                    cid or "pending",
                    turn_id,
                )
            raise
        finally:
            self._release(cid)

    async def _txn_user(self, cid: str, message: str, *, created: bool) -> list[dict]:
        """Transaction A：必要时创建 Conversation，写 USER 并显式 commit。"""
        warns: list[dict] = []
        async with AsyncSessionLocal() as s:
            st, _, _, _ = self._managers(s)
            if created:
                s.add(
                    Conversation(
                        conversation_id=cid,
                        title=(message[:30] if message else "新对话"),
                    )
                )
                await s.flush()
            await st.persist_message(cid, "USER", message)
            await s.commit()
        # post-commit USER cache refresh：以 PG 最近窗口全量替换，避免冷/脏缓存被
        # 单条 append 伪装成完整窗口。
        try:
            await self._refresh_message_cache_after_commit(cid)
        except Exception:
            self._log_degradation(cid, "context", "message_cache", "REDIS_UNAVAILABLE")
            warns.append(
                {
                    "component": "message_cache",
                    "code": "REDIS_UNAVAILABLE",
                    "message": "用户消息缓存刷新失败，已保留 PostgreSQL 真相",
                }
            )
        return warns

    async def _refresh_message_cache_after_commit(self, cid: str) -> None:
        """从 PG 真相重建消息缓存，且 Redis I/O 不与 DB transaction 重叠。

        USER/ASSISTANT 都走同一路径。每次 commit 后的小窗口查询换取缓存自愈：
        即使 Redis 在 USER 阶段不可用、ASSISTANT 阶段恢复，也不会得到仅含回复的
        伪完整缓存。
        """
        async with AsyncSessionLocal() as s:
            st = ShortTermMemoryManager(self.redis, s, self.chat_model)
            messages = await st.read_recent_messages(cid)
        async with AsyncSessionLocal() as s:
            st = ShortTermMemoryManager(self.redis, s, self.chat_model)
            await st.refill_message_cache(cid, messages)

    async def _load_messages(self, cid: str) -> tuple[list[MessageEntry], bool]:
        """Redis-first + PG fallback；所有 Redis await 均位于无活跃事务的 session。"""
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
        if not messages:
            return [], cache_failed

        try:
            async with AsyncSessionLocal() as s:
                st = ShortTermMemoryManager(self.redis, s, self.chat_model)
                await st.refill_message_cache(cid, messages)
        except Exception:
            cache_failed = True
        return messages, cache_failed

    async def _load_summary(self, cid: str) -> tuple[str | None, bool]:
        """Redis-first + PG fallback；PG 读 session 关闭后才回填 Redis。"""
        cache_failed = False
        try:
            async with AsyncSessionLocal() as s:
                st = ShortTermMemoryManager(self.redis, s, self.chat_model)
                summary = await st.read_cached_summary(cid)
        except Exception:
            summary = None
            cache_failed = True
        if summary:
            return summary, cache_failed

        async with AsyncSessionLocal() as s:
            st = ShortTermMemoryManager(self.redis, s, self.chat_model)
            summary = await st.read_summary_from_pg(cid)
        if not summary:
            return None, cache_failed

        try:
            async with AsyncSessionLocal() as s:
                st = ShortTermMemoryManager(self.redis, s, self.chat_model)
                await st.refresh_summary_cache(cid, summary)
        except Exception:
            cache_failed = True
        return summary, cache_failed

    async def _build_context(self, cid, message) -> tuple[str | None, list[tuple[str, str, str]]]:
        """分离外部调用与短 DB session，返回 (prompt, context_warnings)。"""
        warnings: list[tuple[str, str, str]] = []
        try:
            msgs, cache_refill_failed = await self._load_messages(cid)
            if cache_refill_failed:
                warnings.append(
                    self._context_warning(
                        cid,
                        "message_cache",
                        "REDIS_UNAVAILABLE",
                        "消息缓存回填失败，已使用 PostgreSQL 真相",
                    )
                )

            if msgs and msgs[-1].role == "USER" and msgs[-1].content == message:
                msgs = msgs[:-1]  # 排除本轮 USER

            summary, summary_cache_failed = await self._load_summary(cid)
            if summary_cache_failed:
                warnings.append(
                    self._context_warning(
                        cid,
                        "summary_cache",
                        "REDIS_UNAVAILABLE",
                        "摘要缓存读取失败，已使用 PostgreSQL 真相",
                    )
                )
            history_parts = []
            if summary:
                history_parts.append(f"## 历史对话摘要\n{summary}")
            if msgs:
                history_parts.append(
                    "## 最近对话\n" + "\n".join(f"{m.role}: {m.content}" for m in msgs)
                )
            history = "\n\n".join(history_parts)

            long_ctx = ""
            try:
                memory_vector = await self.vector_recall.embed(message)
                async with AsyncSessionLocal() as s:
                    recalled = await self.vector_recall.recall_by_vector(
                        s,
                        LongTermMemory,
                        message,
                        memory_vector,
                        threshold=0.0,
                        top_k=5,
                    )
                if recalled:
                    long_ctx = "\n".join(
                        f"- {memory[0].content} (相似度:{memory[1]:.2f})"
                        for memory in recalled
                    )
            except Exception:
                warnings.append(
                    self._context_warning(
                        cid,
                        "memory_recall",
                        "MEMORY_RECALL_FAILED",
                        "长期记忆召回降级",
                    )
                )

            rag_ctx = ""
            try:
                # prepare_search 完成 QueryRewriter 和全部 embedding；此 session 从未执行 SQL。
                async with AsyncSessionLocal() as s:
                    _, _, rag, _ = self._managers(s)
                    prepared_queries = await rag.prepare_search(message)
                # search_prepared 只执行 SQL，多 query 间不再发生外部 await。
                async with AsyncSessionLocal() as s:
                    _, _, rag, _ = self._managers(s)
                    docs = await rag.search_prepared(prepared_queries, top_k=5)
                    rag_ctx = rag.format_context(docs)
            except Exception:
                warnings.append(
                    self._context_warning(
                        cid,
                        "rag_retrieval",
                        "RAG_FAILED",
                        "知识库检索降级",
                    )
                )

            params = {
                "long_term_memory": long_ctx or "（无）",
                "rag_context": rag_ctx or "（无）",
                "conversation_history": history or "（新对话）",
                "user_message": message,
            }
            async with AsyncSessionLocal() as s:
                pm = PromptTemplateManager(s)
                template = await pm.get_active(PromptType.CHAT)
                if template is None:
                    return None, warnings
                prompt = pm.render_system_prompt(template, params)
        except Exception:
            return None, []
        return prompt, warnings

    async def _txn_assistant(self, cid, text) -> int | None:
        """Transaction B。返回 message_id；None 表示 persist 失败。"""
        try:
            async with AsyncSessionLocal() as s:
                st, _, _, _ = self._managers(s)
                msg = await st.persist_message(cid, "ASSISTANT", text)
                await s.commit()
                return msg.id
        except Exception:
            return None

    async def _post_turn(self, cid: str, assistant_text: str) -> list[dict]:
        """post-turn: ASSISTANT 缓存刷新 + 摘要 + 记忆抽取。返回 warning 列表。"""
        warnings: list[dict] = []
        try:
            await self._refresh_message_cache_after_commit(cid)
        except Exception:
            warnings.append(
                self._post_warning(
                    cid,
                    "message_cache",
                    "REDIS_UNAVAILABLE",
                    "回复缓存刷新失败，已保留 PostgreSQL 真相",
                )
            )
        await self._post_turn_summary(cid, warnings)
        await self._post_turn_extraction(cid, warnings)
        return warnings

    async def _post_turn_summary(self, cid, warnings: list[dict]) -> None:
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
            warnings.append(
                self._post_warning(
                    cid,
                    "summary",
                    "SUMMARY_FAILED",
                    "摘要生成降级",
                )
            )
            return

        if work is None:
            return
        summary_prompt = ShortTermMemoryManager.build_summary_prompt(
            work,
            max_chars=settings.mem_summary_max_chars,
        )
        if summary_prompt is None:
            warnings.append(
                self._post_warning(
                    cid,
                    "summary",
                    "SUMMARY_FAILED",
                    "摘要生成降级",
                )
            )
            return

        try:
            # 上方读取 session 已退出，LLM 调用期间不存在打开的数据库事务。
            summary_text = await st.generate_summary(summary_prompt.text)
        except Exception:
            summary_text = None
        if not summary_text:
            warnings.append(
                self._post_warning(
                    cid,
                    "summary",
                    "SUMMARY_FAILED",
                    "摘要生成降级",
                )
            )
            return

        target_watermark = (
            work.expected_watermark + summary_prompt.included_message_count
        )
        try:
            async with AsyncSessionLocal() as s2:
                st2 = ShortTermMemoryManager(self.redis, s2, self.chat_model)
                updated = await st2.conditional_write_summary(
                    cid,
                    summary_text,
                    expected_watermark=work.expected_watermark,
                    target_watermark=target_watermark,
                )
                if not updated:
                    logger.info(
                        "summary update skipped code=stale_watermark "
                        "conversation_id=%s expected_watermark=%s",
                        cid,
                        work.expected_watermark,
                    )
                    return
                await s2.commit()
        except Exception:
            warnings.append(
                self._post_warning(
                    cid,
                    "summary",
                    "SUMMARY_FAILED",
                    "摘要持久化降级",
                )
            )
            return

        try:
            async with AsyncSessionLocal() as cache_session:
                cache_manager = ShortTermMemoryManager(
                    self.redis,
                    cache_session,
                    self.chat_model,
                )
                # PG 已提交；此 session 未执行 SQL，不存在与 Redis I/O 重叠的事务。
                await cache_manager.refresh_summary_cache(cid, summary_text)
        except Exception:
            warnings.append(
                self._post_warning(
                    cid,
                    "summary_cache",
                    "REDIS_UNAVAILABLE",
                    "摘要缓存刷新失败",
                )
            )

    async def _post_turn_extraction(self, cid, warnings: list[dict]) -> None:
        try:
            msgs, message_cache_failed = await self._load_messages(cid)
            if message_cache_failed:
                warnings.append(
                    self._post_warning(
                        cid,
                        "message_cache",
                        "REDIS_UNAVAILABLE",
                        "消息缓存回填失败，已使用 PostgreSQL 真相",
                    )
                )
            async with AsyncSessionLocal() as s:
                lt = LongTermMemoryManager(s, self.vector_recall)
                has_mem = await lt.has_memories(cid)
            if len(msgs) < MEMORY_EXTRACT_THRESHOLD or has_mem:
                return
            tuples = [(m.role, m.content) for m in msgs]
            facts = await lt.extract_facts_text(tuples, self.chat_model)  # 纯 LLM
            if not facts:
                return
            # 所有 embedding 在一个从未执行 SQL 的 session 中完成。
            async with AsyncSessionLocal() as prepare_session:
                preparer = LongTermMemoryManager(prepare_session, self.vector_recall)
                prepared_facts = await preparer.prepare_facts(facts)
            async with AsyncSessionLocal() as s2:
                lt2 = LongTermMemoryManager(s2, self.vector_recall)
                await lt2.save_prepared_facts(cid, prepared_facts)
                await s2.commit()
        except Exception:
            warnings.append(
                self._post_warning(
                    cid,
                    "memory_extraction",
                    "EXTRACTION_FAILED",
                    "记忆抽取降级",
                )
            )

    async def run_sync(self, prepared: PreparedTurn, message: str) -> TurnResult:
        """同步端点：drain run()，收集 reply + warnings；遇 ChatFailed 抛 ChatTurnFailed。"""
        reply_parts: list[str] = []
        warnings: list[dict] = []
        cid = prepared.conversation_id
        assistant_id = 0
        failed_event: ChatFailed | None = None
        event_gen = self.run(prepared, message)
        try:
            async for ev in event_gen:
                cid = ev.conversation_id or cid
                if isinstance(ev, TokenDelta):
                    reply_parts.append(ev.delta)
                elif isinstance(ev, (ContextWarning, PostTurnWarning)):
                    warnings.append(
                        {
                            "component": ev.component,
                            "code": ev.code,
                            "message": ev.message,
                            "retryable": ev.retryable,
                        }
                    )
                elif isinstance(ev, ChatCompleted):
                    assistant_id = ev.assistant_message_id
                elif isinstance(ev, ChatFailed):
                    # 先让 run() 从 failed yield 恢复并进入 finally 释放 guard，
                    # 再向同步 endpoint 抛出稳定失败。
                    failed_event = ev
        finally:
            await event_gen.aclose()
        if failed_event is not None:
            raise ChatTurnFailed(failed_event)
        return TurnResult(
            conversation_id=cid,
            reply="".join(reply_parts),
            assistant_message_id=assistant_id,
            warnings=warnings,
        )
