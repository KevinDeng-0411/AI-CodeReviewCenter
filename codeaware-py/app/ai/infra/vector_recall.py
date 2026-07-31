"""共享向量召回服务（ADR-0001）。

embed + 内联 pgvector 存储 + cosine 检索；Memory 与 Knowledge 共用，不复制逻辑。
检索策略（纯向量 / 混合 pg_trgm+向量 RRF）作为参数，而非各自一套。
"""

import math
from typing import TypeVar

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class EmbeddingValidationError(ValueError):
    """Embedding provider returned a vector incompatible with Vector(1024)."""


class VectorRecallService:
    def __init__(self, embedder) -> None:
        self.embedder = embedder

    async def embed(self, text: str) -> list[float]:
        embedding = await self.embedder.aembed_query(text)
        if (
            len(embedding) != 1024
            or any(
                not isinstance(value, (int, float)) or not math.isfinite(float(value))
                for value in embedding
            )
        ):
            raise EmbeddingValidationError("embedding must contain 1024 finite values")
        return [float(value) for value in embedding]

    async def store(self, session: AsyncSession, entity: ModelT, text: str) -> ModelT:
        """embed 文本 -> 写入 entity.embedding 内联列 -> add + flush。"""
        embedding = await self.embed(text)
        return await self.store_preembedded(session, entity, embedding)

    async def store_preembedded(
        self, session: AsyncSession, entity: ModelT, embedding: list[float]
    ) -> ModelT:
        """写入已生成的向量；供“先完成全部外部 embedding，再短事务落库”路径使用。"""
        entity.embedding = embedding
        session.add(entity)
        await session.flush()
        return entity

    async def recall(
        self,
        session: AsyncSession,
        model: type[ModelT],
        query_text: str,
        *,
        top_k: int = 5,
        threshold: float = 0.0,
        hybrid: bool = False,
        text_column: str = "content",
        lexical_recall=None,
    ) -> list[tuple[ModelT, float, str]]:
        """语义召回，返回 (entity, score, matchType)。

        hybrid=False 纯向量(matchType='vector')；hybrid=True + lexical_recall 词法+向量 RRF 融合
        (matchType='vector'/'keyword'/'both')。hybrid=True + lexical_recall=None 纯向量(Memory 兼容)。
        """
        qvec = await self.embed(query_text)
        return await self.recall_by_vector(
            session,
            model,
            query_text,
            qvec,
            top_k=top_k,
            threshold=threshold,
            hybrid=hybrid,
            text_column=text_column,
            lexical_recall=lexical_recall,
        )

    async def recall_by_vector(
        self,
        session: AsyncSession,
        model: type[ModelT],
        query_text: str,
        query_vector: list[float],
        *,
        top_k: int = 5,
        threshold: float = 0.0,
        hybrid: bool = False,
        text_column: str = "content",
        lexical_recall=None,
    ) -> list[tuple[ModelT, float, str]]:
        """使用已生成的向量执行纯数据库召回。

        hybrid=False: 纯向量。
        hybrid=True + lexical_recall: 向量 + 词法 RRF 融合。
        hybrid=True + lexical_recall=None: 纯向量（Memory 兼容）。
        """
        emb_col = getattr(model, "embedding")
        vec_stmt = (
            select(model, (1 - emb_col.cosine_distance(query_vector)).label("vec_score"))
            .order_by(emb_col.cosine_distance(query_vector))
            .limit(top_k * 3)
        )
        vec_rows = (await session.execute(vec_stmt)).all()

        if not hybrid or lexical_recall is None:
            return [
                (r[0], round(float(r[1]), 4), "vector")
                for r in vec_rows
                if float(r[1]) >= threshold
            ][:top_k]

        # 混合：词法腿（pg_trgm 或 BM25）+ RRF 融合（ADR-0001 改进②/C4-B）
        lexical_rows = await lexical_recall.search(
            session, model, query_text, text_column=text_column, top_k=top_k
        )
        return self._rrf_fuse(vec_rows, lexical_rows, top_k=top_k, threshold=threshold)

    @staticmethod
    def _rrf_fuse(
        vec_rows: list, kw_rows: list, *, top_k: int, threshold: float, k: int = 60
    ) -> list[tuple]:
        """Reciprocal Rank Fusion：按各腿排名融合，记录 matchType（来源追溯）。"""
        seen: dict[int, list] = {}  # id -> [entity, score, set(legs)]
        for rank, row in enumerate(vec_rows):
            e = row[0]
            seen.setdefault(e.id, [e, 0.0, set()])[1] += 1.0 / (k + rank + 1)
            seen[e.id][2].add("vector")
        for rank, row in enumerate(kw_rows):
            e = row[0]
            seen.setdefault(e.id, [e, 0.0, set()])[1] += 1.0 / (k + rank + 1)
            seen[e.id][2].add("keyword")
        fused = sorted(seen.values(), key=lambda x: x[1], reverse=True)
        out = []
        for e, s, legs in fused:
            if s > threshold:
                mt = "both" if len(legs) > 1 else next(iter(legs))
                out.append((e, round(s, 4), mt))
        return out[:top_k]
