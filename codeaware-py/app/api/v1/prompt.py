"""Prompt API - /api/prompts（版本创建、列表、预览与回滚）。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.prompt.template_manager import PromptTemplateManager
from app.ai.services.prompt import PromptService
from app.api.v1.deps import get_current_user, get_db, require_admin
from app.core.enums import PromptType
from app.core.response import Result
from app.models import User
from app.schemas.prompt import PromptCreateRequest, PromptPreviewVO, PromptTemplateVO

# 全员可读（list/preview）；写操作（create/activate）需 admin
router = APIRouter(prefix="/api/prompts", tags=["Prompt"], dependencies=[Depends(get_current_user)])


def _to_vo(template) -> PromptTemplateVO:
    return PromptTemplateVO.model_validate(template, from_attributes=True)


@router.get("", response_model=Result[list[PromptTemplateVO]])
async def list_prompts(
    type: PromptType | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    svc = PromptService(db, PromptTemplateManager(db))
    templates = await svc.list(type)
    return Result.ok([_to_vo(template) for template in templates])


@router.post("", response_model=Result[PromptTemplateVO])
async def create_prompt(
    request: PromptCreateRequest,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    svc = PromptService(db, PromptTemplateManager(db))
    return Result.ok(_to_vo(await svc.create(request)))


@router.get("/{template_id}/preview", response_model=Result[PromptPreviewVO])
async def preview(
    template_id: int,
    sample_code: str = Query("", max_length=20_000),
    db: AsyncSession = Depends(get_db),
):
    svc = PromptService(db, PromptTemplateManager(db))
    rendered = await svc.preview(template_id, sample_code)
    return Result.ok(PromptPreviewVO(rendered=rendered))


@router.post("/{template_id}/activate", response_model=Result[PromptTemplateVO])
async def activate(template_id: int, db: AsyncSession = Depends(get_db), _admin: User = Depends(require_admin)):
    svc = PromptService(db, PromptTemplateManager(db))
    tpl = await svc.activate(template_id)
    return Result.ok(_to_vo(tpl))
