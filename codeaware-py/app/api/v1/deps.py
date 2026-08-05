"""FastAPI 依赖注入（对应 Java 的 Bean 注入）。"""

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.config import get_chat_model, get_embedding_model, get_vector_recall_service
from app.core.exceptions import BusinessException
from app.db.redis import get_redis
from app.db.session import get_db
from app.models import User

__all__ = [
    "get_db",
    "get_redis",
    "get_chat_model",
    "get_embedding_model",
    "get_vector_recall_service",
    "get_lexical_recall",
    "get_chat_service",
    "get_turn_coordinator",
    "get_current_user",
    "require_admin",
]

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    """从 Authorization: Bearer <token> 解析当前用户。

    测试通过 dependency_overrides 注入测试用户（285 老测试零改动）。
    """
    if creds is None or not creds.credentials:
        raise BusinessException("AUTH_TOKEN_REQUIRED", status_code=401)
    from app.core.security import decode_token

    payload = decode_token(creds.credentials)
    user_id = payload.get("sub")
    if user_id is None:
        raise BusinessException("AUTH_INVALID_TOKEN", status_code=401)
    user = await db.get(User, int(user_id))
    if user is None or not user.is_active:
        raise BusinessException("AUTH_INVALID_TOKEN", status_code=401)
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    """admin 才能通过（建账号、改 Prompt）；member 返回 403。"""
    if user.role != "admin":
        raise BusinessException("AUTH_FORBIDDEN", status_code=403)
    return user


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
