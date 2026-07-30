"""UnitTest API - /api/unit-test（P3-5 薄壳）。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.config import get_chat_model
from app.ai.prompt.template_manager import PromptTemplateManager
from app.ai.services.unit_test import UnitTestService
from app.api.v1.deps import get_db
from app.core.exceptions import BusinessException
from app.core.response import PageResult, Result
from app.models import AiOperationRecord
from app.schemas.entities import AiOperationRecordRead, record_to_dict
from app.schemas.unit_test import UnitTestRequest, UnitTestVO

router = APIRouter(prefix="/api/unit-test", tags=["UnitTest"])


@router.post("/generate", response_model=Result[UnitTestVO])
async def generate(
    req: UnitTestRequest,
    db: AsyncSession = Depends(get_db),
    llm=Depends(get_chat_model),
):
    svc = UnitTestService(db, llm, PromptTemplateManager(db))
    return Result.ok(
        await svc.generate(req.project_name, req.file_path, req.source_code, req.test_framework)
    )


@router.get("/records", response_model=Result[PageResult[AiOperationRecordRead]])
async def list_records(
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    project_name: str | None = Query(default=None, min_length=1, max_length=100),
):
    q = select(AiOperationRecord).where(AiOperationRecord.type == "UNIT_TEST")
    if project_name:
        q = q.where(AiOperationRecord.project_name == project_name)
    q = q.order_by(AiOperationRecord.id.desc()).offset((page - 1) * size).limit(size)
    records = (await db.execute(q)).scalars().all()
    count_q = (
        select(func.count())
        .select_from(AiOperationRecord)
        .where(AiOperationRecord.type == "UNIT_TEST")
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
    if not rec or rec.type != "UNIT_TEST":
        raise BusinessException("UNIT_TEST_RECORD_NOT_FOUND", status_code=404)
    return Result.ok(record_to_dict(rec))
