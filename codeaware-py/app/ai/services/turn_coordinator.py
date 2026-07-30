"""TurnCoordinator - C1-A: Chat 单轮编排状态机。

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

from app.ai.memory.long_term import LongTermMemoryManager
from app.ai.memory.short_term import ShortTermMemoryManager, MessageEntry
from app.ai.prompt.template_manager import PromptTemplateManager
from app.ai.rag.hybrid_retriever import HybridRetriever
from app.ai.rag.query_rewriter import QueryRewriter
from app.ai.rag.semantic_chunker import SemanticChunker
from app.ai.services.rag import RagService
from app.core.enums import PromptType
from app.db.session import AsyncSessionLocal
from app.models import Conversation
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
SUMMARY_THRESHOLD = 10  # C1-A 用现有阈值；C1-B 以 summary_message_count 水位线精修

logger = logging.getLogger(__name__)


class ChatTurnInProgress(Exception):
    def __init__(self, cid: str) -> None:
        super().__init__(f"chat turn in progress: {cid}")
        self.cid = cid


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


class TurnCoordinator:
    _active: set[str] = set()  # 类级 turn guard（local-first 单 worker）

    def __init__(self, chat_model, redis_client, vector_recall, chunker, query_rewriter) -> None:
        self.chat_model = chat_model
        self.redis = redis_client
        self.vector_recall = vector_recall
        self.chunker = chunker
        self.query_rewriter = query_rewriter
        self._owned_guards: set[str] = set()

    def _managers(self, session):
        st = ShortTermMemoryManager(self.redis, session, self.chat_model)
        lt = LongTermMemoryManager(session, self.vector_recall)
        hybrid = HybridRetriever(session, self.vector_recall)
        rag = RagService(session, self.chunker, self.vector_recall, self.query_rewriter, hybrid)
        pm = PromptTemplateManager(session)
        return st, lt, rag, pm

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
        """router 在调用 run/run_sync 前显式获取 turn（同 cid 进行中抛 ChatTurnInProgress -> 409）。"""
        if cid is not None and not self._acquire(cid):
            raise ChatTurnInProgress(cid)

    def release_turn(self, cid: str | None) -> None:
        """响应在 body iterator 尚未启动时也可幂等释放已领用的 guard。"""
        if cid is not None:
            self._release(cid)

    async def run(self, conversation_id: str | None, message: str):
        """产出 typed 事件的 async generator。调用方须先 acquire_turn。"""
        turn_id = uuid.uuid4().hex
        seq = 0

        def nxt() -> int:
            nonlocal seq
            seq += 1
            return seq

        cid = conversation_id
        guard_cid = conversation_id
        terminal_emitted = False

        try:
            # ---- Transaction A: ensure conversation + USER + commit ----
            cid, created, user_warns = await self._txn_user(cid, message)
            if cid is None:
                yield ChatFailed(
                    conversation_id=conversation_id or "", turn_id=turn_id, sequence=nxt(),
                    phase="start",
                    error=ErrorInfo(code="START_FAILED", message="会话初始化失败", retryable=True),
                    partial_output_persisted=False,
                )
                terminal_emitted = True
                return

            # 新会话在 Transaction A commit 后才拥有真实 cid。首事件发出前补领该 cid
            # 的 guard，确保客户端拿到 cid 后，同会话第二个 turn 会稳定返回 409。
            if conversation_id is None:
                if not self._acquire(cid):
                    yield ChatFailed(
                        conversation_id=cid, turn_id=turn_id, sequence=nxt(),
                        phase="start",
                        error=ErrorInfo(
                            code="CHAT_TURN_IN_PROGRESS",
                            message="当前会话已有回复正在生成",
                            retryable=True,
                        ),
                        partial_output_persisted=False,
                    )
                    terminal_emitted = True
                    return
                guard_cid = cid

            yield ChatStarted(conversation_id=cid, turn_id=turn_id, sequence=nxt(), created=created)

            for w in user_warns:
                yield ContextWarning(
                    conversation_id=cid, turn_id=turn_id, sequence=nxt(),
                    component=w["component"], code=w["code"], message=w["message"], retryable=True,
                )

            # ---- build context (exclude current USER) ----
            prompt, ctx_warns = await self._build_context(cid, message)
            if prompt is None:
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
            model_stream = self.chat_model.astream(prompt)
            try:
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
                close_model_stream = getattr(model_stream, "aclose", None)
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
                yield ChatFailed(
                    conversation_id=cid, turn_id=turn_id, sequence=nxt(), phase="persist",
                    error=ErrorInfo(code="PERSIST_FAILED", message="回复持久化失败", retryable=True),
                    partial_output_persisted=False,
                )
                terminal_emitted = True
                return

            # ---- post-turn (cache refresh + summary + extraction) ----
            post_warns = await self._post_turn(cid, text)
            for w in post_warns:
                yield PostTurnWarning(
                    conversation_id=cid, turn_id=turn_id, sequence=nxt(),
                    component=w["component"], code=w["code"], message=w["message"], retryable=True,
                )

            yield ChatCompleted(
                conversation_id=cid, turn_id=turn_id, sequence=nxt(),
                assistant_message_id=assistant_id, warning_count=len(post_warns),
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
            if guard_cid is not None:
                self._release(guard_cid)

    async def _txn_user(self, cid, message) -> tuple[str | None, bool, list[dict]]:
        """Transaction A。返回 (cid, created, warnings)；cid=None 表示 start 失败。"""
        created = False
        warns: list[dict] = []
        try:
            async with AsyncSessionLocal() as s:
                st, _, _, _ = self._managers(s)
                if cid is None:
                    cid = uuid.uuid4().hex
                    created = True
                    s.add(Conversation(conversation_id=cid, title=(message[:30] if message else "新对话")))
                    await s.flush()
                await st.persist_message(cid, "USER", message)
                await s.commit()
        except Exception:
            return None, False, []
        # post-commit USER cache refresh
        try:
            async with AsyncSessionLocal() as s:
                st = ShortTermMemoryManager(self.redis, s, self.chat_model)
                await st.refresh_message_cache(cid, "USER", message)
        except Exception:
            warns.append({"component": "message_cache", "code": "REDIS_UNAVAILABLE",
                          "message": "用户消息缓存刷新失败，已保留 PostgreSQL 真相"})
        return cid, created, warns

    async def _build_context(self, cid, message) -> tuple[str | None, list[tuple[str, str, str]]]:
        """返回 (prompt, context_warnings)；prompt=None 表示构建失败。"""
        warnings: list[tuple[str, str, str]] = []
        try:
            async with AsyncSessionLocal() as s:
                st, lt, rag, pm = self._managers(s)
                msgs = await st.get_messages(cid)
                if msgs and msgs[-1].role == "USER" and msgs[-1].content == message:
                    msgs = msgs[:-1]  # 排除本轮 USER
                history = "\n".join(f"{m.role}: {m.content}" for m in msgs)

                long_ctx = ""
                try:
                    recalled = await lt.recall(message, threshold=0.0, top_k=5)
                    if recalled:
                        long_ctx = "\n".join(f"- {m[0].content} (相似度:{m[1]:.2f})" for m in recalled)
                except Exception:
                    warnings.append(("memory_recall", "MEMORY_RECALL_FAILED", "长期记忆召回降级"))

                rag_ctx = ""
                try:
                    docs = await rag.search(message, top_k=5)
                    rag_ctx = rag.format_context(docs)
                except Exception:
                    warnings.append(("rag_retrieval", "RAG_FAILED", "知识库检索降级"))

                params = {
                    "long_term_memory": long_ctx or "（无）",
                    "rag_context": rag_ctx or "（无）",
                    "conversation_history": history or "（新对话）",
                    "user_message": message,
                }
                template = await pm.get_active(PromptType.CHAT)
                if template:
                    prompt = pm.render_system_prompt(template, params)
                else:
                    prompt = (
                        "你是一个知识渊博的技术助手。\n\n"
                        f"## 长期记忆\n{params['long_term_memory']}\n\n"
                        f"{params['rag_context']}\n\n"
                        f"## 对话历史\n{params['conversation_history']}\n\n"
                        f"## 用户问题\n{message}"
                    )
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
            async with AsyncSessionLocal() as s:
                st = ShortTermMemoryManager(self.redis, s, self.chat_model)
                await st.refresh_message_cache(cid, "ASSISTANT", assistant_text)
        except Exception:
            warnings.append({"component": "message_cache", "code": "REDIS_UNAVAILABLE",
                             "message": "回复缓存刷新失败，已保留 PostgreSQL 真相"})
        await self._post_turn_summary(cid, warnings)
        await self._post_turn_extraction(cid, warnings)
        return warnings

    async def _post_turn_summary(self, cid, warnings: list[dict]) -> None:
        try:
            async with AsyncSessionLocal() as s:
                st = ShortTermMemoryManager(self.redis, s, self.chat_model)
                count = await st.message_count(cid)
                if count < SUMMARY_THRESHOLD:
                    return
                msgs = await st.get_messages(cid)
                existing = await st.get_summary(cid)
                await s.commit()  # 结束读事务，再调 LLM
            summary_text = await st.summarize_text(msgs, existing)  # 纯 LLM
            if not summary_text:
                return
            async with AsyncSessionLocal() as s2:
                st2 = ShortTermMemoryManager(self.redis, s2, self.chat_model)
                await st2.write_summary(cid, summary_text)
                await s2.commit()
            try:
                await st2.refresh_summary_cache(cid, summary_text)
            except Exception:
                warnings.append({"component": "summary_cache", "code": "REDIS_UNAVAILABLE", "message": "摘要缓存刷新失败"})
        except Exception:
            warnings.append({"component": "summary", "code": "SUMMARY_FAILED", "message": "摘要生成降级"})

    async def _post_turn_extraction(self, cid, warnings: list[dict]) -> None:
        try:
            async with AsyncSessionLocal() as s:
                st, lt, _, _ = self._managers(s)
                msgs = await st.get_messages(cid)
                has_mem = await lt.has_memories(cid)
                await s.commit()
            if len(msgs) < MEMORY_EXTRACT_THRESHOLD or has_mem:
                return
            tuples = [(m.role, m.content) for m in msgs]
            facts = await lt.extract_facts_text(tuples, self.chat_model)  # 纯 LLM
            if not facts:
                return
            async with AsyncSessionLocal() as s2:
                lt2 = LongTermMemoryManager(s2, self.vector_recall)
                await lt2.save_facts(cid, facts)
                await s2.commit()
        except Exception:
            warnings.append({"component": "memory_extraction", "code": "EXTRACTION_FAILED", "message": "记忆抽取降级"})

    async def run_sync(self, conversation_id: str | None, message: str) -> TurnResult:
        """同步端点：drain run()，收集 reply + warnings；遇 ChatFailed 抛 ChatTurnFailed。"""
        reply_parts: list[str] = []
        warnings: list[dict] = []
        cid = conversation_id or ""
        assistant_id = 0
        async for ev in self.run(conversation_id, message):
            cid = ev.conversation_id or cid
            if isinstance(ev, TokenDelta):
                reply_parts.append(ev.delta)
            elif isinstance(ev, (ContextWarning, PostTurnWarning)):
                warnings.append({"component": ev.component, "code": ev.code, "message": ev.message})
            elif isinstance(ev, ChatCompleted):
                assistant_id = ev.assistant_message_id
            elif isinstance(ev, ChatFailed):
                raise ChatTurnFailed(ev)
        return TurnResult(
            conversation_id=cid,
            reply="".join(reply_parts),
            assistant_message_id=assistant_id,
            warnings=warnings,
        )
