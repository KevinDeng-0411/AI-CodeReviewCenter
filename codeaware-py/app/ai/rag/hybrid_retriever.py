"""HybridRetriever - RAG 混合检索（词法 + pgvector RRF + matchType，作用 knowledge_chunks）。

向量腿复用 VectorRecallService（embed + 内联 cosine），词法腿由 LexicalRecallPort 提供
（pg_trgm 回退 / BM25 默认目标，C4-B）；RRF 融合 + matchType 来源追溯。
"""

import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.infra.vector_recall import VectorRecallService
from app.ai.rag.lexical_recall import Bm25LexicalRecall, LexicalRecallPort, PgTrgmLexicalRecall
from app.models import KnowledgeChunk

logger = logging.getLogger(__name__)


@dataclass
class ScoredChunk:
    chunk: KnowledgeChunk
    score: float
    match_type: str  # vector / keyword / both


class HybridRetriever:
    def __init__(
        self,
        session: AsyncSession,
        vector_recall: VectorRecallService,
        lexical_recall: LexicalRecallPort,
    ) -> None:
        self.session = session
        self.vector_recall = vector_recall
        self.lexical_recall = lexical_recall
        # 内部日志标识后端类型，不泄漏到公共枚举
        self._backend_name = (
            "bm25" if isinstance(lexical_recall, Bm25LexicalRecall)
            else "pg_trgm" if isinstance(lexical_recall, PgTrgmLexicalRecall)
            else type(lexical_recall).__name__
        )

    async def search(self, query: str, top_k: int = 5) -> list[ScoredChunk]:
        """混合检索：向量 + 词法 RRF 融合，返回带 matchType 的结果。"""
        logger.debug("hybrid search query=%r lexical_backend=%s top_k=%d", query[:80], self._backend_name, top_k)
        results = await self.vector_recall.recall(
            self.session,
            KnowledgeChunk,
            query,
            top_k=top_k,
            hybrid=True,
            text_column="chunk_content",
            lexical_recall=self.lexical_recall,
        )
        return [ScoredChunk(chunk=r[0], score=r[1], match_type=r[2]) for r in results]

    async def search_by_vector(
        self, query: str, query_vector: list[float], top_k: int = 5
    ) -> list[ScoredChunk]:
        """使用预先生成的向量执行纯数据库混合检索。"""
        logger.debug("hybrid search_by_vector query=%r lexical_backend=%s top_k=%d", query[:80], self._backend_name, top_k)
        results = await self.vector_recall.recall_by_vector(
            self.session,
            KnowledgeChunk,
            query,
            query_vector,
            top_k=top_k,
            hybrid=True,
            text_column="chunk_content",
            lexical_recall=self.lexical_recall,
        )
        return [ScoredChunk(chunk=r[0], score=r[1], match_type=r[2]) for r in results]
