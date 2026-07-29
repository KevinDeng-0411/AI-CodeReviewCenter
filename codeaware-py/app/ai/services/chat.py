"""ChatService - 智能问答（核心域，ADR-0004/0005）。

三级上下文整合（长期记忆 + RAG + 短期记忆）+ CHAT 模板 + SSE 流式。
conversation_id 命名（ADR-0004）；CHAT prompt 走模板（ADR-0005）。
"""

import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.memory.long_term import LongTermMemoryManager
from app.ai.memory.short_term import ShortTermMemoryManager
from app.ai.prompt.template_manager import PromptTemplateManager
from app.ai.services.rag import RagService
from app.core.enums import PromptType
from app.models import Conversation, LongTermMemory, Message
from app.schemas.chat import ChatResponseVO

# 对话内生记忆抽取：达 2 轮（4 条消息）后触发一次抽取（ADR-0001 对话内生）。
# inline 执行（复用请求 session，get_db 统一 commit）；SSE 中在 [DONE] 之后抽取，延迟对用户隐藏。
MEMORY_EXTRACT_THRESHOLD = 4


class ChatService:
    def __init__(
        self,
        session: AsyncSession,
        chat_model,
        short_term: ShortTermMemoryManager,
        long_term: LongTermMemoryManager,
        rag_service: RagService,
        prompt_manager: PromptTemplateManager,
    ) -> None:
        self.session = session
        self.chat_model = chat_model
        self.short_term = short_term
        self.long_term = long_term
        self.rag_service = rag_service
        self.prompt_manager = prompt_manager

    async def chat(self, conversation_id: str | None, message: str) -> ChatResponseVO:
        cid = await self._ensure_conversation(conversation_id, message)
        await self.short_term.save_message(cid, "USER", message)
        prompt = await self._build_context_prompt(cid, message)
        reply = await self.chat_model.ainvoke(prompt)
        text = reply.content if hasattr(reply, "content") else str(reply)
        await self.short_term.save_message(cid, "ASSISTANT", text)
        await self._maybe_extract(cid)
        return ChatResponseVO(conversation_id=cid, reply=text)

    async def chat_stream(self, conversation_id: str | None, message: str):
        """SSE 流式：逐 token 推送，结束后保存完整回复。"""
        cid = await self._ensure_conversation(conversation_id, message)
        await self.short_term.save_message(cid, "USER", message)
        prompt = await self._build_context_prompt(cid, message)

        async def gen():
            full: list[str] = []
            async for chunk in self.chat_model.astream(prompt):
                content = chunk.content if hasattr(chunk, "content") else str(chunk)
                full.append(content)
                yield f"data: {content}\n\n"
            await self.short_term.save_message(cid, "ASSISTANT", "".join(full))
            yield "data: [DONE]\n\n"
            # [DONE] 之后再抽取记忆：客户端已解锁输入，抽取延迟对用户隐藏
            await self._maybe_extract(cid)

        return gen()

    async def _ensure_conversation(self, cid: str | None, message: str) -> str:
        if cid:
            return cid
        new_cid = uuid.uuid4().hex
        self.session.add(
            Conversation(conversation_id=new_cid, title=message[:30] if message else "新对话")
        )
        await self.session.flush()
        return new_cid

    async def _build_context_prompt(self, cid: str, message: str) -> str:
        """三级上下文：长期记忆 + RAG + 短期记忆 -> CHAT 模板渲染。"""
        # 长期记忆召回
        long_term_ctx = ""
        try:
            recalled = await self.long_term.recall(message, threshold=0.0, top_k=5)
            if recalled:
                long_term_ctx = "\n".join(
                    f"- {m[0].content} (相似度:{m[1]:.2f})" for m in recalled
                )
        except Exception:
            pass

        # RAG 检索
        rag_ctx = ""
        try:
            docs = await self.rag_service.search(message, top_k=5)
            rag_ctx = self.rag_service.format_context(docs)
        except Exception:
            pass

        # 短期记忆上下文窗口
        conv_history = await self.short_term.get_context_window(cid)

        params = {
            "long_term_memory": long_term_ctx or "（无）",
            "rag_context": rag_ctx or "（无）",
            "conversation_history": conv_history or "（新对话）",
            "user_message": message,
        }

        # CHAT 模板（ADR-0005）
        template = await self.prompt_manager.get_active(PromptType.CHAT)
        if template:
            return self.prompt_manager.render_system_prompt(template, params)

        # fallback：无 CHAT 模板时硬编码
        return (
            "你是一个知识渊博的技术助手。\n\n"
            f"## 长期记忆\n{params['long_term_memory']}\n\n"
            f"{params['rag_context']}\n\n"
            f"## 对话历史\n{params['conversation_history']}\n\n"
            f"## 用户问题\n{message}"
        )

    async def list_conversations(self) -> list[Conversation]:
        r = await self.session.execute(select(Conversation).order_by(Conversation.id.desc()))
        return list(r.scalars().all())

    async def get_messages(self, cid: str) -> list:
        return await self.short_term.get_messages(cid)

    async def delete_conversation(self, cid: str) -> None:
        await self.short_term.clear(cid)
        await self.session.execute(delete(Conversation).where(Conversation.conversation_id == cid))
        await self.session.execute(delete(Message).where(Message.conversation_id == cid))
        await self.session.flush()

    # ---------- 对话内生记忆抽取（ADR-0001）----------

    async def _maybe_extract(self, cid: str) -> None:
        """达阈值且该会话尚无记忆 -> 抽取一次原子事实写入长期记忆（inline，复用请求 session）。"""
        msgs = await self.short_term.get_messages(cid)
        if len(msgs) >= MEMORY_EXTRACT_THRESHOLD and not await self._has_memories(cid):
            try:
                await self.long_term.extract_from_conversation(cid, self.chat_model)
            except Exception:
                # 抽取失败不影响主流程（记忆是增益，非关键路径）
                pass

    async def _has_memories(self, cid: str) -> bool:
        cnt = await self.session.scalar(
            select(func.count())
            .select_from(LongTermMemory)
            .where(LongTermMemory.conversation_id == cid)
        )
        return (cnt or 0) > 0
