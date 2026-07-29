"""Memory API - /api/memory（长期记忆录入+语义搜索+删除）。"""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.memory.long_term import LongTermMemoryManager
from app.api.v1.deps import get_db, get_vector_recall_service
from app.core.response import Result

router = APIRouter(prefix="/api/memory", tags=["Memory"])


class MemorySaveRequest(BaseModel):
    content: str
    memory_type: str = "KNOWLEDGE"
    conversation_id: str | None = None
    metadata: dict | None = None


@router.post("/long-term")
async def save_long_term(
    req: MemorySaveRequest,
    db: AsyncSession = Depends(get_db),
    vr=Depends(get_vector_recall_service),
):
    mgr = LongTermMemoryManager(db, vr)
    mem = await mgr.save_memory(req.content, req.memory_type, req.conversation_id, req.metadata)
    return Result.ok({"id": mem.id, "content": mem.content})


@router.get("/long-term/search")
async def search_long_term(
    query: str = Query(...),
    threshold: float = Query(0.3),
    top_k: int = Query(5),
    db: AsyncSession = Depends(get_db),
    vr=Depends(get_vector_recall_service),
):
    mgr = LongTermMemoryManager(db, vr)
    results = await mgr.recall(query, top_k=top_k, threshold=threshold)
    return Result.ok(
        [
            {
                "id": r[0].id,
                "content": r[0].content,
                "memory_type": r[0].memory_type,
                "conversation_id": r[0].conversation_id,
                "source": (r[0].meta or {}).get("source", "manual"),
                "similarity": r[1],
            }
            for r in results
        ]
    )


@router.delete("/long-term/{memory_id}")
async def delete_long_term(memory_id: int, db: AsyncSession = Depends(get_db)):
    from app.models import LongTermMemory
    mem = await db.get(LongTermMemory, memory_id)
    if mem:
        await db.delete(mem)
        await db.commit()
    return Result.ok()
