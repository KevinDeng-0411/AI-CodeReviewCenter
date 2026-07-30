"""P3-1：CodeReviewService 结构化输出 + 计数 + 持久化（mock LLM）。"""

import pytest

from app.ai.prompt.template_manager import PromptTemplateManager
from app.ai.services.code_review import CodeReviewService
from app.core.enums import PromptType
from app.core.exceptions import BusinessException
from app.models import AiOperationRecord
from app.schemas.code_review import CodeReviewResult, ReviewIssue


class _FakeStructured:
    def __init__(self, result, fails=False):
        self.result = result
        self.fails = fails

    async def ainvoke(self, prompt, **kw):
        if self.fails:
            raise RuntimeError("structured unavailable")
        return self.result


class FakeChatModel:
    """模拟 with_structured_output(schema, method=...).ainvoke -> CodeReviewResult。

    structured_fails=True 时强制走 ainvoke 回退路径（返回 JSON 字符串）。
    """

    def __init__(self, result, *, structured_fails=False):
        self.result = result
        self.structured_fails = structured_fails

    def with_structured_output(self, schema, **kw):
        return _FakeStructured(self.result, fails=self.structured_fails)

    async def ainvoke(self, prompt, **kw):
        class _R:
            content = self.result.model_dump_json()

        return _R()


@pytest.fixture
async def cr_template(db_session):
    pm = PromptTemplateManager(db_session)
    return await pm.save_and_activate(
        PromptType.CODE_REVIEW,
        name="v1",
        role_setting="你是评审专家",
        template_body="评审: {{source_code}}",
        review_dimensions="代码质量,安全性",
        severity_levels="Critical,Warning,Info",
    )


def _sample_result() -> CodeReviewResult:
    return CodeReviewResult(
        summary="有安全漏洞",
        score=40,
        issues=[
            ReviewIssue(
                dimension="安全性", severity="Critical", line_range="1-2", title="SQL注入",
                description="d", suggestion="s", fix_code="c",
            ),
            ReviewIssue(
                dimension="性能", severity="Warning", line_range="3", title="N+1",
                description="d", suggestion="s",
            ),
            ReviewIssue(
                dimension="风格", severity="Info", line_range="1", title="命名",
                description="d", suggestion="s",
            ),
        ],
        highlights=["注释完整"],
    )


async def test_review_parses_counts_and_persists(db_session, cr_template):
    svc = CodeReviewService(db_session, FakeChatModel(_sample_result()), PromptTemplateManager(db_session))
    vo = await svc.review("proj", "src/Foo.java", "public void foo(){}")

    assert vo.summary == "有安全漏洞"
    assert vo.score == 40
    assert vo.issues_count == 3
    assert vo.critical_count == 1
    assert vo.warning_count == 1
    assert vo.info_count == 1
    assert vo.highlights == ["注释完整"]
    assert vo.id is not None  # 已持久化

    rec = await db_session.get(AiOperationRecord, vo.id)
    assert rec.type == "CODE_REVIEW"
    assert rec.project_name == "proj"
    assert rec.file_path == "src/Foo.java"
    assert rec.prompt_template_id == cr_template.id
    assert rec.meta["critical_count"] == 1
    assert rec.meta["issues_count"] == 3
    assert "summary" in rec.result  # 原始 JSON 留存


async def test_review_no_template_raises(db_session):
    svc = CodeReviewService(
        db_session,
        FakeChatModel(CodeReviewResult(summary="empty", score=0, issues=[])),
        PromptTemplateManager(db_session),
    )
    with pytest.raises(BusinessException):
        await svc.review("proj", "f", "code")


async def test_review_empty_issues_zero_counts(db_session, cr_template):
    result = CodeReviewResult(summary="干净", score=95, issues=[], highlights=[])
    svc = CodeReviewService(db_session, FakeChatModel(result), PromptTemplateManager(db_session))
    vo = await svc.review("proj", "f", "code")
    assert vo.issues_count == 0
    assert vo.critical_count == 0
    assert vo.warning_count == 0
    assert vo.info_count == 0


async def test_review_fallback_ainvoke_when_structured_fails(db_session, cr_template):
    """with_structured_output 失败 -> 回退 ainvoke + Pydantic 解析（§10）。"""
    result = _sample_result()
    svc = CodeReviewService(
        db_session, FakeChatModel(result, structured_fails=True), PromptTemplateManager(db_session)
    )
    vo = await svc.review("proj", "f", "code")
    assert vo.issues_count == 3
    assert vo.critical_count == 1
    assert vo.id is not None  # 回退路径也持久化
