"""async engine + session 工厂 - 对应 Java 数据源配置。

P0 仅建立引擎与 session 工厂（惰性连接，PG 未起也不影响导入）；
P1 起模型与 CRUD 实际使用。get_db 作为 FastAPI Depends。
"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

engine = create_async_engine(
    settings.pg_url_async,
    echo=False,
    pool_size=8,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    """FastAPI 依赖：每请求一个 async session。

    成功时 commit（service 层只 flush 不 commit，统一在此落盘）；
    异常时 rollback。测试通过 dependency_overrides 注入带回滚的 db_session，不受影响。
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
