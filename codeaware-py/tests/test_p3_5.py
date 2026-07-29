"""P3-5：薄工具服务测试 - UnitTest / AiReadme / DocumentParser / PromptService。"""

import pytest

from app.ai.prompt.template_manager import PromptTemplateManager
from app.ai.services.ai_readme import AiReadmeService
from app.ai.services.document_parser import DocumentParserService
from app.ai.services.prompt import PromptService
from app.ai.services.unit_test import UnitTestService
from app.core.enums import PromptType
from app.schemas.ai_readme import AiReadmeResult
from app.schemas.unit_test import UnitTestResult


# ---------- 带 with_structured_output 的 LLM fake（conftest FakeLLM 不支持） ----------
class _FakeStructured:
    def __init__(self, result):
        self.result = result

    async def ainvoke(self, prompt, **kw):
        return self.result


class FakeStructuredLLM:
    def __init__(self, result):
        self.result = result

    def with_structured_output(self, schema, **kw):
        return _FakeStructured(self.result)

    async def ainvoke(self, prompt, **kw):
        class _R:
            content = "pong"

        return _R()


# ---------- UnitTestService ----------
@pytest.fixture
async def unit_test_template(db_session):
    pm = PromptTemplateManager(db_session)
    return await pm.save_and_activate(
        PromptType.UNIT_TEST,
        name="v1",
        role_setting="你是测试工程师",
        template_body="为以下代码生成 {{test_framework}} 测试：\n```\n{{source_code}}\n```",
    )


async def test_unit_test_generate_persists_record(db_session, unit_test_template):
    llm = FakeStructuredLLM(UnitTestResult(test_code="class TestFoo { @Test void x(){} }", test_framework="JUnit5"))
    svc = UnitTestService(db_session, llm, PromptTemplateManager(db_session))
    vo = await svc.generate("proj", "Foo.java", "public class Foo {}", test_framework="JUnit5")
    assert vo.id is not None
    assert vo.test_framework == "JUnit5"
    assert vo.test_code  # 非空


async def test_unit_test_no_template_raises(db_session):
    llm = FakeStructuredLLM(UnitTestResult(test_code="x", test_framework="JUnit5"))
    svc = UnitTestService(db_session, llm, PromptTemplateManager(db_session))
    from app.core.exceptions import BusinessException

    with pytest.raises(BusinessException):
        await svc.generate("p", "f", "code")


# ---------- AiReadmeService ----------
@pytest.fixture
async def readme_template(db_session):
    pm = PromptTemplateManager(db_session)
    return await pm.save_and_activate(
        PromptType.AI_README,
        name="v1",
        role_setting="你是文档工程师",
        template_body="为 {{project_name}} 生成 README（路径：{{project_path}}）",
    )


async def test_ai_readme_generate_and_get(db_session, readme_template):
    llm = FakeStructuredLLM(AiReadmeResult(content="# my-project\n\nREADME content"))
    svc = AiReadmeService(db_session, llm, PromptTemplateManager(db_session))
    vo = await svc.generate("my-project", "/path/to/proj")
    assert vo.id is not None
    assert vo.project_name == "my-project"
    got = await svc.get("my-project")
    assert got is not None
    assert got.id == vo.id


# ---------- DocumentParserService ----------
async def test_document_parser_plain_markdown():
    text = await DocumentParserService().parse(b"# Title\n\nBody text", "test.md")
    assert "Title" in text or "Body" in text


async def test_document_parser_empty():
    text = await DocumentParserService().parse(b"", "empty.md")
    assert isinstance(text, str)


# ---------- PromptService ----------
async def test_prompt_service_list_and_activate(db_session):
    pm = PromptTemplateManager(db_session)
    # 含 {{source_code}} 占位符以便 preview 验证替换
    await pm.save_and_activate(
        PromptType.CODE_REVIEW, name="cr1", role_setting="r", template_body="Hello {{source_code}}!"
    )
    await pm.save_and_activate(
        PromptType.UNIT_TEST, name="ut1", role_setting="r", template_body="b"
    )
    svc = PromptService(db_session, pm)
    all_t = await svc.list()
    assert len(all_t) >= 2
    cr_only = await svc.list("CODE_REVIEW")
    assert all(t.type == "CODE_REVIEW" for t in cr_only)
    assert len(cr_only) >= 1
    # preview：含占位符的模板应替换
    tpl = cr_only[0]
    rendered = await svc.preview(tpl.id, "sample code")
    assert "sample code" in rendered
    # activate
    await pm.save_and_activate(
        PromptType.CODE_REVIEW, name="cr2", role_setting="r", template_body="b2"
    )
    cr_after = await svc.list("CODE_REVIEW")
    active = [t for t in cr_after if t.is_active]
    assert len(active) == 1
    assert active[0].name == "cr2"
