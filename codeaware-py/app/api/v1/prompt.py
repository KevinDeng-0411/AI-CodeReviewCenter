"""Prompt API - /api/prompts（模板列表+预览+激活，P3-5 用 PromptService 封装）。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.prompt.template_manager import PromptTemplateManager
from app.ai.services.prompt import PromptService
from app.api.v1.deps import get_db
from app.core.response import Result

router = APIRouter(prefix="/api/prompts", tags=["Prompt"])


@router.get("")
async def list_prompts(type: str | None = Query(None), db: AsyncSession = Depends(get_db)):
    svc = PromptService(db, PromptTemplateManager(db))
    templates = await svc.list(type)
    return Result.ok(
        [
            {"id": t.id, "type": t.type, "version": t.version, "name": t.name, "is_active": t.is_active}
            for t in templates
        ]
    )


@router.get("/{template_id}/preview")
async def preview(
    template_id: int,
    sample_code: str = Query(""),
    db: AsyncSession = Depends(get_db),
):
    svc = PromptService(db, PromptTemplateManager(db))
    rendered = await svc.preview(template_id, sample_code)
    return Result.ok(
        {"rendered": rendered[:200] + "..." if len(rendered) > 200 else rendered}
    )


@router.post("/{template_id}/activate")
async def activate(template_id: int, db: AsyncSession = Depends(get_db)):
    svc = PromptService(db, PromptTemplateManager(db))
    tpl = await svc.activate(template_id)
    return Result.ok({"id": tpl.id, "version": tpl.version, "is_active": tpl.is_active})
