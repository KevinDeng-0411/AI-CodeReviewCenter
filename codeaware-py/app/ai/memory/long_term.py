"""LongTermMemoryManager - 情景/语义记忆（ADR-0001）。

原子事实 + 内联 pgvector 向量；embed/store/recall 全走共享 VectorRecallService，
不复制逻辑。默认纯向量召回（混合检索是 Knowledge 的事）。
对话内生：从对话抽取原子事实落库（conversation_id 关联），与外部 Knowledge 文档分野。
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.infra.vector_recall import VectorRecallService
from app.models import LongTermMemory, Message
from app.schemas.code_review import _extract_json
from app.schemas.memory import ExtractedFacts

EXTRACT_PROMPT = """你是记忆抽取器。从以下对话中提取值得长期记忆的原子事实。

要求：
- 每条是一个完整、原子、可独立召回的陈述（不含代词指代，如「用户使用 FastAPI + SQLAlchemy 2.0」而非「他用 FastAPI」）
- 只提取：用户偏好、技术决策、项目约束、重要背景、事实性结论
- 跳过寒暄、临时性内容、纯解释性回复
- 最多 5 条；若无值得记忆的内容，返回空数组

对话：
{convo}

严格以 JSON 返回：{{"facts": ["事实1", "事实2"]}}"""


class LongTermMemoryManager:
    def __init__(self, session: AsyncSession, vector_recall: VectorRecallService) -> None:
        self.session = session
        self.vector_recall = vector_recall

    async def save_memory(
        self,
        content: str,
        memory_type: str,
        conversation_id: str | None = None,
        metadata: dict | None = None,
    ) -> LongTermMemory:
        mem = LongTermMemory(
            content=content,
            memory_type=memory_type,
            conversation_id=conversation_id,
            meta=metadata,
        )
        # embed + 内联写 Vector 列 + add + flush（共享服务，ADR-0001）
        await self.vector_recall.store(self.session, mem, content)
        return mem

    async def recall(
        self, query: str, top_k: int = 5, threshold: float = 0.0
    ) -> list[tuple[LongTermMemory, float]]:
        """纯向量语义召回（hybrid=False）。"""
        return await self.vector_recall.recall(
            self.session, LongTermMemory, query, top_k=top_k, threshold=threshold
        )

    async def delete(self, memory_id: int) -> None:
        mem = await self.session.get(LongTermMemory, memory_id)
        if mem:
            await self.session.delete(mem)
            await self.session.flush()

    async def extract_from_conversation(self, cid: str, chat_model) -> int:
        """从对话抽取原子事实 -> 落库（memory_type=FACT，conversation_id 关联，ADR-0001 对话内生）。

        取最近 10 条消息 -> LLM 抽取 -> 每条事实 save_memory（embed+内联）。
        返回新增事实数。
        """
        r = await self.session.execute(
            select(Message.role, Message.content)
            .where(Message.conversation_id == cid)
            .order_by(Message.id.desc())
            .limit(10)
        )
        rows = list(reversed(r.all()))
        if not rows:
            return 0
        convo = "\n".join(f"{role}: {content}" for role, content in rows)
        prompt = EXTRACT_PROMPT.format(convo=convo)
        facts = await self._invoke_extract(chat_model, prompt)
        for fact in facts:
            fact = fact.strip()
            if not fact:
                continue
            await self.save_memory(
                fact, "FACT", cid, {"source": "conversation"}
            )
        await self.session.flush()
        return len(facts)

    async def _invoke_extract(self, chat_model, prompt: str) -> list[str]:
        """结构化抽取（json_mode），失败回退 ainvoke + 解析。"""
        try:
            structured = chat_model.with_structured_output(ExtractedFacts, method="json_mode")
            result: ExtractedFacts = await structured.ainvoke(prompt)
            return result.facts
        except Exception:
            raw = await chat_model.ainvoke(prompt)
            return ExtractedFacts.model_validate_json(_extract_json(raw.content)).facts

