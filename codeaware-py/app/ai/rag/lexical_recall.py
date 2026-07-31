"""C4-B: 词法召回端口 - pg_trgm 回退 / BM25 默认目标。

VectorRecallService 不再内联 pg_trgm；词法腿由此 Port 提供。
RRF 只用排名（enumerate），score 值不参与融合计算。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TypeVar

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class LexicalRecallPort(ABC):
    """词法召回窄接口：按词法相关性返回 (entity, score) 降序列表。"""

    @abstractmethod
    async def search(
        self,
        session: AsyncSession,
        model: type[ModelT],
        query_text: str,
        *,
        text_column: str = "content",
        top_k: int = 5,
    ) -> list[tuple[ModelT, float]]:
        """返回 (entity, score)，按词法相关性降序。RRF 只用排名。"""
        ...


class PgTrgmLexicalRecall(LexicalRecallPort):
    """pg_trgm similarity 回退后端（C3 默认）。"""

    async def search(
        self,
        session: AsyncSession,
        model: type[ModelT],
        query_text: str,
        *,
        text_column: str = "content",
        top_k: int = 5,
    ) -> list[tuple[ModelT, float]]:
        txt_col = getattr(model, text_column)
        stmt = (
            select(model, func.similarity(txt_col, query_text).label("kw_score"))
            .where(func.similarity(txt_col, query_text) > 0.1)
            .order_by(func.similarity(txt_col, query_text).desc())
            .limit(top_k * 3)
        )
        rows = (await session.execute(stmt)).all()
        return [(r[0], float(r[1])) for r in rows]


class Bm25LexicalRecall(LexicalRecallPort):
    """ParadeDB pg_search BM25 后端（C4 目标）。

    使用 @@@ 操作符 + chinese_compatible tokenizer。
    扩展/索引不可用时返回空列表（降级为纯向量），不抛异常。
    """

    async def search(
        self,
        session: AsyncSession,
        model: type[ModelT],
        query_text: str,
        *,
        text_column: str = "content",
        top_k: int = 5,
    ) -> list[tuple[ModelT, float]]:
        try:
            # @@ @ 右边必须 text literal（不能用参数）；转义单引号后内联
            q = query_text.replace("'", "''")
            stmt = (
                select(model)
                .where(
                    __import__("sqlalchemy").text(
                        f"{model.__tablename__}.{text_column} @@@ '{q}'"
                    )
                )
                .limit(top_k * 3)
            )
            rows = (await session.execute(stmt)).scalars().all()
            # RRF 只用排名；score 给 0.0（顺序由 @@@ BM25 排序保证）
            return [(r, 0.0) for r in rows]
        except Exception:
            # pg_search 扩展不存在 / 索引不存在 / 查询失败 -> 空列表，降级纯向量
            return []
