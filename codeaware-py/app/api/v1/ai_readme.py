"""AIReadMe API backed by a safe local project snapshot."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.config import get_chat_model
from app.ai.prompt.template_manager import PromptTemplateManager
from app.ai.services.ai_readme import AiReadmeService
from app.ai.services.project_snapshot import ProjectSnapshotService
from app.api.v1.deps import get_db, get_current_user
from app.core.response import Result
from app.schemas.ai_readme import AiReadmeCapability, AiReadmeRequest, AiReadmeVO

router = APIRouter(prefix="/api/ai-readme", tags=["AIReadMe"], dependencies=[Depends(get_current_user)])


def get_project_snapshot_service() -> ProjectSnapshotService:
    return ProjectSnapshotService.from_settings()


@router.get("/capabilities", response_model=Result[AiReadmeCapability])
async def capabilities(
    snapshot_service: ProjectSnapshotService = Depends(get_project_snapshot_service),
):
    enabled, reason = snapshot_service.capability()
    return Result.ok(AiReadmeCapability(enabled=enabled, reason=reason))


@router.post("/generate", response_model=Result[AiReadmeVO])
async def generate(
    req: AiReadmeRequest,
    db: AsyncSession = Depends(get_db),
    llm=Depends(get_chat_model),
    snapshot_service: ProjectSnapshotService = Depends(get_project_snapshot_service),
):
    service = AiReadmeService(
        db,
        llm,
        PromptTemplateManager(db),
        snapshot_service,
    )
    return Result.ok(await service.generate(req.project_name, req.project_path))


@router.get("/{project_name}", response_model=Result[AiReadmeVO | None])
async def get_readme(
    project_name: str,
    db: AsyncSession = Depends(get_db),
    llm=Depends(get_chat_model),
):
    service = AiReadmeService(db, llm, PromptTemplateManager(db))
    return Result.ok(await service.get(project_name))
