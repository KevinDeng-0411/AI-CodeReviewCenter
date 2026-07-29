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
    "get_chat_service",
]


async def get_chat_service(
    db: AsyncSession = Depends(get_db),
    llm=Depends(get_chat_model),
    redis=Depends(get_redis),
    vr=Depends(get_vector_recall_service),
):
    """构造 ChatService（三级上下文整合，依赖较多，集中工厂）。"""
    from app.ai.memory.long_term import LongTermMemoryManager
    from app.ai.memory.short_term import ShortTermMemoryManager
    from app.ai.prompt.template_manager import PromptTemplateManager
    from app.ai.rag.hybrid_retriever import HybridRetriever
    from app.ai.rag.query_rewriter import QueryRewriter
    from app.ai.rag.semantic_chunker import SemanticChunker
    from app.ai.services.chat import ChatService
    from app.ai.services.rag import RagService

    short_term = ShortTermMemoryManager(redis, db, llm)
    long_term = LongTermMemoryManager(db, vr)
    chunker = SemanticChunker()
    rag = RagService(db, chunker, vr, QueryRewriter(llm), HybridRetriever(db, vr))
    pm = PromptTemplateManager(db)
    return ChatService(db, llm, short_term, long_term, rag, pm)
