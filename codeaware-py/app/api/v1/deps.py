"""FastAPI 依赖注入（对应 Java 的 Bean 注入）。"""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.config import get_chat_model, get_embedding_model, get_vector_recall_service
from app.db.redis import get_redis
from app.db.session import get_db

__all__ = [
    "get_db",
    "get_redis",
    "get_chat_model",
    "get_embedding_model",
    "get_vector_recall_service",
    "get_lexical_recall",
    "get_chat_service",
    "get_turn_coordinator",
]


async def get_lexical_recall():
    """C4-B: 按 rag_lexical_backend 配置选择词法召回后端（pg_trgm 回退 / bm25 目标）。"""
    from app.ai.rag.lexical_recall import Bm25LexicalRecall, PgTrgmLexicalRecall
    from app.core.config import settings

    if settings.rag_lexical_backend == "bm25":
        return Bm25LexicalRecall()
    return PgTrgmLexicalRecall()


async def get_turn_coordinator(
    llm=Depends(get_chat_model),
    redis=Depends(get_redis),
    vr=Depends(get_vector_recall_service),
    lr=Depends(get_lexical_recall),
):
    """构造 TurnCoordinator（C1-A：Chat 单轮编排，自管 session/事务/事件）。"""
    from app.ai.rag.query_rewriter import QueryRewriter
    from app.ai.rag.semantic_chunker import SemanticChunker
    from app.ai.services.turn_coordinator import TurnCoordinator

    return TurnCoordinator(llm, redis, vr, SemanticChunker(), QueryRewriter(llm), lr)


async def get_chat_service(
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    """构造 ChatService（会话查询/删除；Turn 编排在 TurnCoordinator）。"""
    from app.ai.services.chat import ChatService

    return ChatService(db, redis)
