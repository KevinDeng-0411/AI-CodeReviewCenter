"""AIReadMe API - /api/ai-readme（P3-5 薄壳）。"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.config import get_chat_model
from app.ai.prompt.template_manager import PromptTemplateManager
from app.ai.services.ai_readme import AiReadmeService
from app.api.v1.deps import get_db
from app.core.response import Result
from app.schemas.ai_readme import AiReadmeRequest

router = APIRouter(prefix="/api/ai-readme", tags=["AIReadMe"])


@router.post("/generate")
async def generate(
    req: AiReadmeRequest,
    db: AsyncSession = Depends(get_db),
    llm=Depends(get_chat_model),
):
    svc = AiReadmeService(db, llm, PromptTemplateManager(db))
    return Result.ok(await svc.generate(req.project_name, req.project_path))


@router.get("/{project_name}")
async def get_readme(
    project_name: str,
    db: AsyncSession = Depends(get_db),
    llm=Depends(get_chat_model),
):
    svc = AiReadmeService(db, llm, PromptTemplateManager(db))
    return Result.ok(await svc.get(project_name))
