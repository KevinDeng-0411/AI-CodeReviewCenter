"""C2-B：Code Review 与 Unit Test 的 route-level 闭环验收。"""

from dataclasses import dataclass, field

import pytest
from sqlalchemy import func, select

from app.ai.config import get_chat_model
from app.ai.prompt.template_manager import PromptTemplateManager
from app.core.enums import PromptType
from app.db.session import get_db
from app.main import app
from app.models import AiOperationRecord
from app.schemas.code_review import CodeReviewResult, ReviewIssue
from app.schemas.unit_test import UnitTestResult


def _code_review_result() -> CodeReviewResult:
    return CodeReviewResult(
        summary="发现一项高风险问题",
        score=52,
        issues=[
            ReviewIssue(
                dimension="安全性",
                severity="Critical",
                line_range="2",
                title="SQL 注入",
                description="SQL 使用字符串拼接",
                suggestion="改用参数化查询",
                fix_code="jdbc.query(sql, userId)",
            )
        ],
        highlights=["职责清晰"],
    )


@dataclass
class _RouteModel:
    mode: str = "ok"
    prompts: list[str] = field(default_factory=list)

    def with_structured_output(self, schema, **_kwargs):
        owner = self

        class _Structured:
            async def ainvoke(self, prompt, **_kwargs):
                owner.prompts.append(prompt)
                if owner.mode == "timeout":
                    raise TimeoutError("redacted upstream timeout")
                if owner.mode == "invalid":
                    raise RuntimeError("force invalid fallback")
                if schema is CodeReviewResult:
                    return _code_review_result()
                if schema is UnitTestResult:
                    return UnitTestResult(
                        test_code=(
                            "class CalculatorTest {\n"
                            "  @Test void addsNumbers() { assertEquals(3, new Calculator().add(1, 2)); }\n"
                            "}"
                        ),
                        test_framework="JUnit5",
                    )
                raise AssertionError(f"unexpected schema: {schema}")

        return _Structured()

    async def ainvoke(self, prompt, **_kwargs):
        self.prompts.append(prompt)

        class _Raw:
            content = "not-json"

        return _Raw()


@pytest.fixture
async def c2b_context(db_session):
    manager = PromptTemplateManager(db_session)
    cr_v1 = await manager.save_and_activate(
        PromptType.CODE_REVIEW,
        name="C2-B CR v1",
        role_setting="CR_ROLE_V1",
        template_body="CR_TEMPLATE_V1\n{{source_code}}",
        review_dimensions="安全性",
        severity_levels="Critical,Warning,Info",
    )
    cr_v2 = await manager.save_and_activate(
        PromptType.CODE_REVIEW,
        name="C2-B CR v2",
        role_setting="CR_ROLE_V2",
        template_body="CR_TEMPLATE_V2\n{{source_code}}",
        review_dimensions="安全性",
        severity_levels="Critical,Warning,Info",
    )
    unit_template = await manager.save_and_activate(
        PromptType.UNIT_TEST,
        name="C2-B Unit Test",
        role_setting="UNIT_ROLE",
        template_body=(
            "UNIT_TEMPLATE\n"
            "file={{file_path}}\nframework={{test_framework}}\n{{source_code}}"
        ),
    )
    model = _RouteModel()
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_chat_model] = lambda: model
    try:
        yield {
            "model": model,
            "cr_v1": cr_v1,
            "cr_v2": cr_v2,
            "unit_template": unit_template,
        }
    finally:
        app.dependency_overrides.clear()


def _review_payload(project_name: str = "c2b-project") -> dict:
    return {
        "project_name": project_name,
        "file_path": "src/OrderService.java",
        "source_code": 'jdbc.execute("select * from orders where id=" + orderId);',
    }


def _unit_payload(project_name: str = "c2b-project") -> dict:
    return {
        "project_name": project_name,
        "file_path": "src/Calculator.java",
        "source_code": "class Calculator { int add(int a, int b) { return a + b; } }",
        "test_framework": "JUnit5",
    }


async def test_code_review_selected_and_active_template_are_traceable(client, c2b_context):
    model = c2b_context["model"]
    selected = _review_payload("selected-project")
    selected["prompt_template_id"] = c2b_context["cr_v1"].id

    selected_response = await client.post("/api/code-review/review", json=selected)
    assert selected_response.status_code == 200
    selected_data = selected_response.json()["data"]
    assert "CR_TEMPLATE_V1" in model.prompts[-1]
    assert "CR_TEMPLATE_V2" not in model.prompts[-1]

    selected_record = await client.get(
        f"/api/code-review/records/{selected_data['id']}"
    )
    assert selected_record.status_code == 200
    assert (
        selected_record.json()["data"]["prompt_template_id"]
        == c2b_context["cr_v1"].id
    )

    active_response = await client.post(
        "/api/code-review/review",
        json=_review_payload("active-project"),
    )
    assert active_response.status_code == 200
    active_data = active_response.json()["data"]
    assert active_data["critical_count"] == 1
    assert active_data["issues_count"] == 1
    assert "CR_TEMPLATE_V2" in model.prompts[-1]

    active_record = await client.get(
        f"/api/code-review/records/{active_data['id']}"
    )
    assert (
        active_record.json()["data"]["prompt_template_id"]
        == c2b_context["cr_v2"].id
    )


async def test_records_are_filtered_counted_and_type_isolated(client, c2b_context):
    first = await client.post(
        "/api/code-review/review",
        json=_review_payload("project-a"),
    )
    second = await client.post(
        "/api/code-review/review",
        json=_review_payload("project-b"),
    )
    unit = await client.post(
        "/api/unit-test/generate",
        json=_unit_payload("project-a"),
    )
    assert first.status_code == second.status_code == unit.status_code == 200

    filtered = await client.get(
        "/api/code-review/records",
        params={"project_name": "project-a", "page": 1, "size": 10},
    )
    page = filtered.json()["data"]
    assert page["total"] == 1
    assert len(page["records"]) == 1
    assert page["records"][0]["project_name"] == "project-a"

    wrong_code_review_detail = await client.get(
        f"/api/code-review/records/{unit.json()['data']['id']}"
    )
    assert wrong_code_review_detail.status_code == 404
    assert wrong_code_review_detail.json()["msg"] == "CODE_REVIEW_RECORD_NOT_FOUND"

    wrong_unit_detail = await client.get(
        f"/api/unit-test/records/{first.json()['data']['id']}"
    )
    assert wrong_unit_detail.status_code == 404
    assert wrong_unit_detail.json()["msg"] == "UNIT_TEST_RECORD_NOT_FOUND"


async def test_unit_test_generation_persists_framework_and_code(client, c2b_context):
    response = await client.post("/api/unit-test/generate", json=_unit_payload())
    assert response.status_code == 200
    generated = response.json()["data"]
    assert generated["test_framework"] == "JUnit5"
    assert "@Test" in generated["test_code"]
    assert "UNIT_TEMPLATE" in c2b_context["model"].prompts[-1]
    assert "framework=JUnit5" in c2b_context["model"].prompts[-1]

    detail = await client.get(f"/api/unit-test/records/{generated['id']}")
    record = detail.json()["data"]
    assert record["type"] == "UNIT_TEST"
    assert record["metadata"]["test_framework"] == "JUnit5"
    assert "@Test" in record["result"]

    records = await client.get(
        "/api/unit-test/records",
        params={"project_name": "c2b-project", "page": 1, "size": 10},
    )
    assert records.json()["data"]["total"] == 1


@pytest.mark.parametrize(
    ("path", "payload", "expected_code"),
    [
        (
            "/api/code-review/review",
            {**_review_payload(), "source_code": "   "},
            "CODE_REVIEW_REQUEST_INVALID",
        ),
        (
            "/api/code-review/review",
            {**_review_payload(), "source_code": "x" * 100_001},
            "CODE_REVIEW_REQUEST_INVALID",
        ),
        (
            "/api/unit-test/generate",
            {**_unit_payload(), "test_framework": "pytest"},
            "UNIT_TEST_REQUEST_INVALID",
        ),
    ],
)
async def test_invalid_requests_use_stable_error_envelopes(
    client,
    c2b_context,
    path,
    payload,
    expected_code,
):
    response = await client.post(path, json=payload)
    assert response.status_code == 422
    assert response.json() == {"code": 0, "msg": expected_code, "data": None}


@pytest.mark.parametrize(
    ("path", "payload", "mode", "status", "expected_code"),
    [
        (
            "/api/code-review/review",
            _review_payload(),
            "timeout",
            504,
            "CODE_REVIEW_MODEL_TIMEOUT",
        ),
        (
            "/api/unit-test/generate",
            _unit_payload(),
            "invalid",
            502,
            "UNIT_TEST_OUTPUT_INVALID",
        ),
    ],
)
async def test_model_failure_does_not_create_audit_record(
    client,
    db_session,
    c2b_context,
    path,
    payload,
    mode,
    status,
    expected_code,
):
    c2b_context["model"].mode = mode
    response = await client.post(path, json=payload)
    assert response.status_code == status
    assert response.json() == {"code": 0, "msg": expected_code, "data": None}
    assert await db_session.scalar(select(func.count()).select_from(AiOperationRecord)) == 0


async def test_c2b_demo_code_review_unit_test_route_closure(client, c2b_context):
    review = await client.post(
        "/api/code-review/review",
        json=_review_payload("c2b-demo"),
    )
    unit = await client.post(
        "/api/unit-test/generate",
        json=_unit_payload("c2b-demo"),
    )
    records = await client.get(
        "/api/code-review/records",
        params={"project_name": "c2b-demo"},
    )

    assert review.status_code == unit.status_code == records.status_code == 200
    assert records.json()["data"]["total"] == 1
    print(
        "C2-B demo:",
        {
            "review_id": review.json()["data"]["id"],
            "critical_count": review.json()["data"]["critical_count"],
            "unit_test_id": unit.json()["data"]["id"],
            "framework": unit.json()["data"]["test_framework"],
            "review_records": records.json()["data"]["total"],
        },
    )
