"""FastAPI 依赖注入（对应 Java 的 Bean 注入）。"""

from app.ai.config import get_chat_model, get_embedding_model, get_vector_recall_service
from app.db.redis import get_redis
from app.db.session import get_db

__all__ = [
    "get_db",
    "get_redis",
    "get_chat_model",
    "get_embedding_model",
    "get_vector_recall_service",
]
