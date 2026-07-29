"""PromptService - Prompt 模板管理（list/activate/preview，P3-5 路由层封装）。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.prompt.template_manager import PromptTemplateManager
from app.core.exceptions import BusinessException
from app.models import PromptTemplate


class PromptService:
    def __init__(self, session: AsyncSession, prompt_manager: PromptTemplateManager) -> None:
        self.session = session
        self.prompt_manager = prompt_manager

    async def list(self, type_: str | None = None) -> list[PromptTemplate]:
        q = select(PromptTemplate).order_by(PromptTemplate.id.desc())
        if type_:
            q = q.where(PromptTemplate.type == type_)
        return list((await self.session.execute(q)).scalars().all())

    async def activate(self, template_id: int) -> PromptTemplate:
        return await self.prompt_manager.activate(template_id)

    async def preview(self, template_id: int, sample_code: str = "") -> str:
        tpl = await self.session.get(PromptTemplate, template_id)
        if not tpl:
            raise BusinessException("模板不存在")
        params = {"source_code": sample_code} if sample_code else {}
        return self.prompt_manager.render(tpl, params)
