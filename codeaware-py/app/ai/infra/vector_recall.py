"""共享向量召回服务（ADR-0001）。

embed + 内联 pgvector 存储 + cosine 检索；Memory 与 Knowledge 共用，不复制逻辑。
检索策略（纯向量 / 混合 pg_trgm+向量 RRF）作为参数，而非各自一套。
"""

from typing import TypeVar

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class VectorRecallService:
    def __init__(self, embedder) -> None:
        self.embedder = embedder

    async def embed(self, text: str) -> list[float]:
        return await self.embedder.aembed_query(text)

    async def store(self, session: AsyncSession, entity: ModelT, text: str) -> ModelT:
        """embed 文本 -> 写入 entity.embedding 内联列 -> add + flush。"""
        entity.embedding = await self.embed(text)
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
    ) -> list[tuple[ModelT, float]]:
        """语义召回。hybrid=False 纯向量；hybrid=True 关键词(pg_trgm)+向量 RRF 融合。"""
        qvec = await self.embed(query_text)
        emb_col = getattr(model, "embedding")
        vec_stmt = (
            select(model, (1 - emb_col.cosine_distance(qvec)).label("vec_score"))
            .order_by(emb_col.cosine_distance(qvec))
            .limit(top_k * 3)
        )
        vec_rows = (await session.execute(vec_stmt)).all()

        if not hybrid:
            return [
                (r[0], round(float(r[1]), 4)) for r in vec_rows if float(r[1]) >= threshold
            ][:top_k]

        # 混合：pg_trgm 关键词腿 + RRF 融合（ADR-0001 改进②）
        txt_col = getattr(model, text_column)
        kw_stmt = (
            select(model, func.similarity(txt_col, query_text).label("kw_score"))
            .where(func.similarity(txt_col, query_text) > 0.1)
            .order_by(func.similarity(txt_col, query_text).desc())
            .limit(top_k * 3)
        )
        kw_rows = (await session.execute(kw_stmt)).all()
        return self._rrf_fuse(vec_rows, kw_rows, top_k=top_k, threshold=threshold)

    @staticmethod
    def _rrf_fuse(
        vec_rows: list, kw_rows: list, *, top_k: int, threshold: float, k: int = 60
    ) -> list[tuple]:
        """Reciprocal Rank Fusion：按各腿排名融合，不依赖原始分数量纲。"""
        scores: dict[int, list] = {}
        for rank, row in enumerate(vec_rows):
            entity = row[0]
            scores.setdefault(entity.id, [entity, 0.0])[1] += 1.0 / (k + rank + 1)
        for rank, row in enumerate(kw_rows):
            entity = row[0]
            scores.setdefault(entity.id, [entity, 0.0])[1] += 1.0 / (k + rank + 1)
        fused = sorted(scores.values(), key=lambda x: x[1], reverse=True)
        return [(e, round(s, 4)) for e, s in fused if s > threshold][:top_k]
