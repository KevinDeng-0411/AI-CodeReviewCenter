"""LongTermMemoryManager - 情景/语义记忆（ADR-0001）。

原子事实 + 内联 pgvector 向量；embed/store/recall 全走共享 VectorRecallService，
不复制逻辑。默认纯向量召回（混合检索是 Knowledge 的事）。
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.infra.vector_recall import VectorRecallService
from app.models import LongTermMemory


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
