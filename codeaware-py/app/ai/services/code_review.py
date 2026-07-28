"""CodeReviewService - AI 代码评审（改进③ 结构化输出 + ADR-0005 版本化模板 + ADR-0006 持久化）。

流程：取激活 CODE_REVIEW 模板 -> 渲染 -> with_structured_output(CodeReviewResult)
     -> 计数(critical/warning/info) -> 持久化 ai_operation_records。
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.prompt.template_manager import PromptTemplateManager
from app.core.enums import PromptType
from app.core.exceptions import BusinessException
from app.models import AiOperationRecord
from app.schemas.code_review import CodeReviewResult, CodeReviewVO


class CodeReviewService:
    def __init__(
        self,
        session: AsyncSession,
        chat_model,
        prompt_manager: PromptTemplateManager,
    ) -> None:
        self.session = session
        self.chat_model = chat_model
        self.prompt_manager = prompt_manager

    async def review(
        self,
        project_name: str,
        file_path: str,
        source_code: str,
        conversation_id: str | None = None,
    ) -> CodeReviewVO:
        template = await self.prompt_manager.get_active(PromptType.CODE_REVIEW)
        if template is None:
            raise BusinessException("未找到可用的 CODE_REVIEW Prompt 模板")

        system_prompt = self.prompt_manager.render_system_prompt(
            template, {"source_code": source_code}
        )
        structured = self.chat_model.with_structured_output(CodeReviewResult)
        result: CodeReviewResult = await structured.ainvoke(system_prompt)

        vo = self._to_vo(result, project_name, file_path)

        record = AiOperationRecord(
            type=PromptType.CODE_REVIEW.value,
            project_name=project_name,
            file_path=file_path,
            source_code=source_code,
            result=result.model_dump_json(),
            prompt_template_id=template.id,
            ai_model=vo.ai_model,
            meta={
                "score": vo.score,
                "issues_count": vo.issues_count,
                "critical_count": vo.critical_count,
                "warning_count": vo.warning_count,
                "info_count": vo.info_count,
            },
        )
        self.session.add(record)
        await self.session.flush()
        vo.id = record.id
        return vo

    @staticmethod
    def _to_vo(result: CodeReviewResult, project_name: str, file_path: str) -> CodeReviewVO:
        issues = result.issues

        def count(sev: str) -> int:
            return sum(1 for i in issues if i.severity.strip().lower() == sev)

        return CodeReviewVO(
            project_name=project_name,
            file_path=file_path,
            summary=result.summary,
            score=result.score,
            issues=issues,
            highlights=result.highlights,
            issues_count=len(issues),
            critical_count=count("critical"),
            warning_count=count("warning"),
            info_count=count("info"),
        )
