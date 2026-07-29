"""UnitTestService - AI 单元测试生成（P3-5 薄壳，复用 CodeReview 模式 + ADR-0005/0006）。"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.config import get_chat_model  # type: ignore  # for factory hint
from app.ai.prompt.template_manager import PromptTemplateManager
from app.core.enums import PromptType
from app.core.exceptions import BusinessException
from app.models import AiOperationRecord
from app.schemas.code_review import _extract_json  # 复用 JSON 提取工具
from app.schemas.unit_test import UnitTestResult, UnitTestVO


class UnitTestService:
    def __init__(
        self,
        session: AsyncSession,
        chat_model,
        prompt_manager: PromptTemplateManager,
    ) -> None:
        self.session = session
        self.chat_model = chat_model
        self.prompt_manager = prompt_manager

    async def generate(
        self, project_name: str, file_path: str, source_code: str, test_framework: str = "JUnit5"
    ) -> UnitTestVO:
        template = await self.prompt_manager.get_active(PromptType.UNIT_TEST)
        if template is None:
            raise BusinessException("未找到 UNIT_TEST Prompt 模板")
        params = {
            "source_code": source_code,
            "file_path": file_path,
            "test_framework": test_framework,
        }
        system_prompt = self.prompt_manager.render_system_prompt(template, params)
        result = await self._invoke_structured(system_prompt, test_framework)
        vo = UnitTestVO(
            project_name=project_name, file_path=file_path,
            test_code=result.test_code, test_framework=result.test_framework or test_framework,
        )
        record = AiOperationRecord(
            type=PromptType.UNIT_TEST.value,
            project_name=project_name, file_path=file_path, source_code=source_code,
            result=result.test_code, prompt_template_id=template.id, ai_model=vo.ai_model,
            meta={"test_framework": vo.test_framework, "test_code_lines": len(result.test_code.splitlines())},
        )
        self.session.add(record)
        await self.session.flush()
        vo.id = record.id
        return vo

    async def _invoke_structured(self, system_prompt: str, test_framework: str) -> UnitTestResult:
        """结构化输出：thinking 模式用 json_mode，失败回退 ainvoke + Pydantic 解析。"""
        try:
            structured = self.chat_model.with_structured_output(UnitTestResult, method="json_mode")
            return await structured.ainvoke(system_prompt)
        except Exception:
            raw = await self.chat_model.ainvoke(system_prompt)
            return UnitTestResult.model_validate_json(_extract_json(raw.content))
