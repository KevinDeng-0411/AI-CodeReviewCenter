"""AiReadmeService - AIReadMe 生成（P3-5 薄壳，复用 CodeReview 模式 + 存入 ai_readme_documents）。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.prompt.template_manager import PromptTemplateManager
from app.core.enums import PromptType
from app.core.exceptions import BusinessException
from app.models import AiReadmeDocument
from app.schemas.ai_readme import AiReadmeResult, AiReadmeVO
from app.schemas.code_review import _extract_json


class AiReadmeService:
    def __init__(
        self,
        session: AsyncSession,
        chat_model,
        prompt_manager: PromptTemplateManager,
    ) -> None:
        self.session = session
        self.chat_model = chat_model
        self.prompt_manager = prompt_manager

    async def generate(self, project_name: str, project_path: str) -> AiReadmeVO:
        template = await self.prompt_manager.get_active(PromptType.AI_README)
        if template is None:
            raise BusinessException("未找到 AI_README Prompt 模板")
        params = {"project_name": project_name, "project_path": project_path}
        system_prompt = self.prompt_manager.render_system_prompt(template, params)
        result = await self._invoke_structured(system_prompt)
        vo = AiReadmeVO(project_name=project_name, title=project_name, content=result.content)
        record = AiReadmeDocument(
            project_name=project_name, section="README", content=result.content, version=1
        )
        self.session.add(record)
        await self.session.flush()
        vo.id = record.id
        return vo

    async def get(self, project_name: str) -> AiReadmeVO | None:
        r = await self.session.execute(
            select(AiReadmeDocument)
            .where(AiReadmeDocument.project_name == project_name)
            .order_by(AiReadmeDocument.id.desc())
            .limit(1)
        )
        rec = r.scalar_one_or_none()
        if not rec:
            return None
        return AiReadmeVO(id=rec.id, project_name=rec.project_name, title=rec.project_name, content=rec.content)

    async def _invoke_structured(self, system_prompt: str) -> AiReadmeResult:
        try:
            structured = self.chat_model.with_structured_output(AiReadmeResult, method="json_mode")
            return await structured.ainvoke(system_prompt)
        except Exception:
            raw = await self.chat_model.ainvoke(system_prompt)
            return AiReadmeResult.model_validate_json(_extract_json(raw.content))
