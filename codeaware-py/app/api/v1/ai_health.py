"""AI 基建连通性自测（P2）：LLM + Embedding + pgvector 三通验证。

真实调用外部 API，属集成端点；测试以 mock 验证接线，真实连通性手动访问。
"""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from app.ai.config import get_chat_model, get_embedding_model
from app.core.response import Result
from app.db.session import get_db
from app.models import KnowledgeChunk

router = APIRouter(prefix="/api/ai", tags=["AI 基建"])


@router.get("/health")
async def ai_health(
    llm=Depends(get_chat_model),
    embedder=Depends(get_embedding_model),
    db=Depends(get_db),
):
    status = {"llm": False, "embedding": False, "dim": None, "pgvector": False}

    try:
        await llm.ainvoke("ping")
        status["llm"] = True
    except Exception as e:  # noqa: BLE001
        status["llm_error"] = str(e)

    try:
        vec = await embedder.aembed_query("ping")
        status["dim"] = len(vec)
        status["embedding"] = len(vec) == 1024
    except Exception as e:  # noqa: BLE001
        status["embedding_error"] = str(e)

    try:
        await db.scalar(select(func.count(KnowledgeChunk.id)))
        status["pgvector"] = True
    except Exception as e:  # noqa: BLE001
        status["pgvector_error"] = str(e)

    return Result.ok(status)
