"""Memory API - /api/memory（长期记忆录入+语义搜索+删除）。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.memory.long_term import LongTermMemoryManager
from app.api.v1.deps import get_db, get_vector_recall_service, get_current_user
from app.core.exceptions import BusinessException
from app.core.response import Result
from app.models import Conversation, LongTermMemory
from app.schemas.memory import MemoryHit, MemoryListItem, MemoryListVO, MemorySaveRequest, MemorySaveVO

router = APIRouter(prefix="/api/memory", tags=["Memory"], dependencies=[Depends(get_current_user)])


@router.post("/long-term", response_model=Result[MemorySaveVO])
async def save_long_term(
    req: MemorySaveRequest,
    db: AsyncSession = Depends(get_db),
    vr=Depends(get_vector_recall_service),
):
    if req.conversation_id is not None:
        exists = await db.scalar(
            select(Conversation.id).where(
                Conversation.conversation_id == req.conversation_id
            )
        )
        if exists is None:
            raise BusinessException(
                "MEMORY_CONVERSATION_NOT_FOUND",
                status_code=404,
            )
    mgr = LongTermMemoryManager(db, vr)
    try:
        mem = await mgr.save_memory(
            req.content,
            req.memory_type.value,
            req.conversation_id,
            req.metadata,
        )
    except Exception as exc:
        raise BusinessException("MEMORY_EMBEDDING_FAILED", status_code=502) from exc
    return Result.ok(MemorySaveVO(id=mem.id, content=mem.content))


@router.get("/long-term", response_model=Result[MemoryListVO])
async def list_long_term(
    memory_type: str = Query("ALL", pattern="^(ALL|FACT|REFERENCE)$"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """列出全部长期记忆，支持按类型过滤 + 分页。"""
    base = select(LongTermMemory).order_by(LongTermMemory.id.desc())
    count_stmt = select(func.count()).select_from(LongTermMemory)
    if memory_type != "ALL":
        base = base.where(LongTermMemory.memory_type == memory_type)
        count_stmt = count_stmt.where(LongTermMemory.memory_type == memory_type)
    total = await db.scalar(count_stmt) or 0
    rows = (await db.execute(base.offset((page - 1) * size).limit(size))).scalars().all()
    return Result.ok(MemoryListVO(
        total=total, page=page, size=size,
        records=[
            MemoryListItem(
                id=r.id, content=r.content, memory_type=r.memory_type,
                conversation_id=r.conversation_id,
                source=(r.meta or {}).get("source", "manual"),
                created_at=r.created_at.isoformat() if r.created_at else "",
            )
            for r in rows
        ],
    ))


@router.get("/long-term/search", response_model=Result[list[MemoryHit]])
async def search_long_term(
    query: str = Query(..., min_length=1, max_length=1_000),
    threshold: float = Query(0.3, ge=0.0, le=1.0),
    top_k: int = Query(5, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
    vr=Depends(get_vector_recall_service),
):
    mgr = LongTermMemoryManager(db, vr)
    try:
        results = await mgr.recall(query, top_k=top_k, threshold=threshold)
    except Exception as exc:
        raise BusinessException("MEMORY_EMBEDDING_FAILED", status_code=502) from exc
    return Result.ok(
        [
            MemoryHit(
                id=r[0].id,
                content=r[0].content,
                memory_type=r[0].memory_type,
                conversation_id=r[0].conversation_id,
                source=(r[0].meta or {}).get("source", "manual"),
                similarity=r[1],
            )
            for r in results
        ]
    )


@router.delete("/long-term/{memory_id}", response_model=Result[None])
async def delete_long_term(memory_id: int, db: AsyncSession = Depends(get_db)):
    mem = await db.get(LongTermMemory, memory_id)
    if mem is None:
        raise BusinessException("MEMORY_NOT_FOUND", status_code=404)
    await db.delete(mem)
    await db.commit()
    return Result.ok()
