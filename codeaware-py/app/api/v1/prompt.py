"""Prompt API - /api/prompts（模板列表+预览+激活，ADR-0005）。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.prompt.template_manager import PromptTemplateManager
from app.api.v1.deps import get_db
from app.core.exceptions import BusinessException
from app.core.response import Result

router = APIRouter(prefix="/api/prompts", tags=["Prompt"])


@router.get("")
async def list_prompts(type: str | None = Query(None), db: AsyncSession = Depends(get_db)):
    pm = PromptTemplateManager(db)
    from app.models import PromptTemplate
    from sqlalchemy import select
    q = select(PromptTemplate).order_by(PromptTemplate.id.desc())
    if type:
        q = q.where(PromptTemplate.type == type)
    templates = (await db.execute(q)).scalars().all()
    return Result.ok(
        [
            {"id": t.id, "type": t.type, "version": t.version, "name": t.name, "is_active": t.is_active}
            for t in templates
        ]
    )


@router.get("/{template_id}/preview")
async def preview(template_id: int, sample_code: str = Query(""), db: AsyncSession = Depends(get_db)):
    pm = PromptTemplateManager(db)
    from app.models import PromptTemplate
    tpl = await db.get(PromptTemplate, template_id)
    if not tpl:
        raise BusinessException("模板不存在")
    rendered = pm.render(tpl, {"source_code": sample_code} if sample_code else {})
    return Result.ok({"rendered": rendered[:200] + "..." if len(rendered) > 200 else rendered})


@router.post("/{template_id}/activate")
async def activate(template_id: int, db: AsyncSession = Depends(get_db)):
    pm = PromptTemplateManager(db)
    tpl = await pm.activate(template_id)
    return Result.ok({"id": tpl.id, "version": tpl.version, "is_active": tpl.is_active})
