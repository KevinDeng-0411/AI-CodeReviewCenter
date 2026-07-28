"""通用 async Repository - 基础 CRUD，替代 Java 11 个 Mapper 接口。

每个模型实例化一个 Repository(session, Model) 即可，无需重复样板。
"""

from typing import Generic, Sequence, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class Repository(Generic[ModelT]):
    def __init__(self, session: AsyncSession, model: type[ModelT]) -> None:
        self.session = session
        self.model = model

    async def get(self, pk: int) -> ModelT | None:
        return await self.session.get(self.model, pk)

    async def list(self, *, offset: int = 0, limit: int = 50) -> Sequence[ModelT]:
        result = await self.session.execute(
            select(self.model).offset(offset).limit(limit)
        )
        return result.scalars().all()

    async def add(self, obj: ModelT) -> ModelT:
        self.session.add(obj)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def delete(self, obj: ModelT) -> None:
        await self.session.delete(obj)
        await self.session.flush()
