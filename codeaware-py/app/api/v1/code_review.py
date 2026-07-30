"""Code Review API - /api/code-review。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.prompt.template_manager import PromptTemplateManager
from app.ai.services.code_review import CodeReviewService
from app.api.v1.deps import get_chat_model, get_db
from app.core.exceptions import BusinessException
from app.core.response import PageResult, Result
from app.models import AiOperationRecord
from app.schemas.code_review import CodeReviewRequest, CodeReviewVO
from app.schemas.entities import AiOperationRecordRead, record_to_dict

router = APIRouter(prefix="/api/code-review", tags=["Code Review"])


@router.post("/review", response_model=Result[CodeReviewVO])
async def review(req: CodeReviewRequest, db: AsyncSession = Depends(get_db), llm=Depends(get_chat_model)):
    svc = CodeReviewService(db, llm, PromptTemplateManager(db))
    vo = await svc.review(req.project_name, req.file_path, req.source_code, req.prompt_template_id)
    return Result.ok(vo)


@router.get("/records", response_model=Result[PageResult[AiOperationRecordRead]])
async def list_records(
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    project_name: str | None = Query(default=None, min_length=1, max_length=100),
):
    q = select(AiOperationRecord).where(AiOperationRecord.type == "CODE_REVIEW")
    if project_name:
        q = q.where(AiOperationRecord.project_name == project_name)
    q = q.order_by(AiOperationRecord.id.desc()).offset((page - 1) * size).limit(size)
    records = (await db.execute(q)).scalars().all()
    count_q = (
        select(func.count())
        .select_from(AiOperationRecord)
        .where(AiOperationRecord.type == "CODE_REVIEW")
    )
    if project_name:
        count_q = count_q.where(AiOperationRecord.project_name == project_name)
    total = await db.scalar(count_q)
    return Result.ok(
        {"total": total or 0, "page": page, "size": size, "records": [record_to_dict(r) for r in records]}
    )


@router.get("/records/{record_id}", response_model=Result[AiOperationRecordRead])
async def get_record(record_id: int, db: AsyncSession = Depends(get_db)):
    rec = await db.get(AiOperationRecord, record_id)
    if not rec or rec.type != "CODE_REVIEW":
        raise BusinessException("CODE_REVIEW_RECORD_NOT_FOUND", status_code=404)
    return Result.ok(record_to_dict(rec))
