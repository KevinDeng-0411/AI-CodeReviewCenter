"""HybridRetriever - RAG 混合检索（pg_trgm + pgvector RRF + matchType，作用 knowledge_chunks）。

向量腿复用 VectorRecallService（embed + 内联 cosine），关键词腿 pg_trgm；
RRF 融合 + matchType 来源追溯（ADR-0001 改进②）。单查询；多查询改写+去重在 RagService（P3-4）。
"""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.infra.vector_recall import VectorRecallService
from app.models import KnowledgeChunk


@dataclass
class ScoredChunk:
    chunk: KnowledgeChunk
    score: float
    match_type: str  # vector / keyword / both


class HybridRetriever:
    def __init__(self, session: AsyncSession, vector_recall: VectorRecallService) -> None:
        self.session = session
        self.vector_recall = vector_recall

    async def search(self, query: str, top_k: int = 5) -> list[ScoredChunk]:
        """混合检索：向量 + 关键词 RRF 融合，返回带 matchType 的结果。"""
        results = await self.vector_recall.recall(
            self.session,
            KnowledgeChunk,
            query,
            top_k=top_k,
            hybrid=True,
            text_column="chunk_content",
        )
        return [ScoredChunk(chunk=r[0], score=r[1], match_type=r[2]) for r in results]

    async def search_by_vector(
        self, query: str, query_vector: list[float], top_k: int = 5
    ) -> list[ScoredChunk]:
        """使用预先生成的向量执行纯数据库混合检索。"""
        results = await self.vector_recall.recall_by_vector(
            self.session,
            KnowledgeChunk,
            query,
            query_vector,
            top_k=top_k,
            hybrid=True,
            text_column="chunk_content",
        )
        return [ScoredChunk(chunk=r[0], score=r[1], match_type=r[2]) for r in results]
