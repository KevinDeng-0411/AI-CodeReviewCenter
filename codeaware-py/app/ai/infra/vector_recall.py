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
    ) -> list[tuple[ModelT, float, str]]:
        """语义召回，返回 (entity, score, matchType)。

        hybrid=False 纯向量(matchType='vector')；hybrid=True 关键词(pg_trgm)+向量 RRF 融合
        (matchType='vector'/'keyword'/'both')。
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
    ) -> list[tuple[ModelT, float, str]]:
        """使用已生成的向量执行纯数据库召回。

        调用方可先在无数据库事务时完成远程 embedding，再在短 session 中调用本方法；
        本方法自身不执行任何模型或网络调用。
        """
        emb_col = getattr(model, "embedding")
        vec_stmt = (
            select(model, (1 - emb_col.cosine_distance(query_vector)).label("vec_score"))
            .order_by(emb_col.cosine_distance(query_vector))
            .limit(top_k * 3)
        )
        vec_rows = (await session.execute(vec_stmt)).all()

        if not hybrid:
            return [
                (r[0], round(float(r[1]), 4), "vector")
                for r in vec_rows
                if float(r[1]) >= threshold
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
