"""PromptService - Prompt 模板创建、版本化、预览与回滚。"""

import re
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.prompt.template_manager import PromptTemplateManager
from app.core.enums import PromptType
from app.core.exceptions import BusinessException
from app.models import PromptTemplate
from app.schemas.prompt import PromptCreateRequest

_PLACEHOLDER_PATTERN = re.compile(r"\{\{([a-z_][a-z0-9_]*)\}\}")
_PLACEHOLDERS = {
    PromptType.CODE_REVIEW: {"source_code"},
    PromptType.UNIT_TEST: {"source_code", "file_path", "test_framework"},
    PromptType.AI_README: {"project_name", "project_path"},
    PromptType.CHAT: {
        "long_term_memory",
        "rag_context",
        "conversation_history",
        "user_message",
    },
}
_PREVIEW_SAMPLES = {
    PromptType.CODE_REVIEW: {"source_code": "public class Example {}"},
    PromptType.UNIT_TEST: {
        "source_code": "public int add(int a, int b) { return a + b; }",
        "file_path": "src/Example.java",
        "test_framework": "JUnit5",
    },
    PromptType.AI_README: {
        "project_name": "example-project",
        "project_path": "[server-approved local snapshot]",
    },
    PromptType.CHAT: {
        "long_term_memory": "用户使用 FastAPI",
        "rag_context": "项目采用 PostgreSQL",
        "conversation_history": "USER: 示例问题",
        "user_message": "请总结项目架构",
    },
}


class PromptService:
    def __init__(self, session: AsyncSession, prompt_manager: PromptTemplateManager) -> None:
        self.session = session
        self.prompt_manager = prompt_manager

    async def list(self, type_: str | None = None) -> list[PromptTemplate]:
        q = select(PromptTemplate).order_by(PromptTemplate.id.desc())
        if type_:
            q = q.where(PromptTemplate.type == type_)
        return list((await self.session.execute(q)).scalars().all())

    async def create(self, request: PromptCreateRequest) -> PromptTemplate:
        self._validate_placeholders(request.type, request.template_body)
        return await self.prompt_manager.save_and_activate(
            request.type,
            name=request.name,
            role_setting=request.role_setting,
            template_body=request.template_body,
            review_dimensions=request.review_dimensions,
            severity_levels=request.severity_levels,
        )

    async def activate(self, template_id: int) -> PromptTemplate:
        return await self.prompt_manager.activate(template_id)

    async def preview(self, template_id: int, sample_code: str = "") -> str:
        tpl = await self.session.get(PromptTemplate, template_id)
        if not tpl:
            raise BusinessException("PROMPT_NOT_FOUND", status_code=404)
        type_ = PromptType(tpl.type)
        params = dict(_PREVIEW_SAMPLES[type_])
        if type_ == PromptType.CODE_REVIEW and sample_code:
            params["source_code"] = sample_code
        return self.prompt_manager.render_system_prompt(tpl, params)

    @staticmethod
    def _validate_placeholders(type_: PromptType, template_body: str) -> None:
        actual = set(_PLACEHOLDER_PATTERN.findall(template_body))
        required = _PLACEHOLDERS[type_]
        missing = sorted(required - actual)
        unknown = sorted(actual - required)
        if missing:
            raise BusinessException("PROMPT_REQUIRED_PLACEHOLDERS_MISSING")
        if unknown:
            raise BusinessException("PROMPT_UNKNOWN_PLACEHOLDER")
