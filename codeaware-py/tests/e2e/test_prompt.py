"""C2-C：Prompt 版本管理的 route-level 与并发闭环。"""

import asyncio

import pytest
from sqlalchemy import delete, func, select

from app.ai.prompt.template_manager import PromptTemplateManager
from app.ai.services.prompt import PromptService
from app.core.enums import PromptType
from app.db.session import AsyncSessionLocal, get_db
from app.main import app
from app.models import PromptTemplate
from app.schemas.prompt import PromptCreateRequest


_VALID_BODIES = {
    PromptType.CODE_REVIEW: "评审：{{source_code}}",
    PromptType.UNIT_TEST: (
        "文件：{{file_path}}\n框架：{{test_framework}}\n源码：{{source_code}}"
    ),
    PromptType.AI_README: "项目：{{project_name}}\n路径：{{project_path}}",
    PromptType.CHAT: (
        "记忆：{{long_term_memory}}\n知识：{{rag_context}}\n"
        "历史：{{conversation_history}}\n用户：{{user_message}}"
    ),
}


@pytest.fixture
async def c2c_context(db_session):
    manager = PromptTemplateManager(db_session)
    seeds = {}
    for type_ in PromptType:
        seeds[type_] = await manager.save_and_activate(
            type_,
            name=f"C2-C {type_.value} v1",
            role_setting=f"ROLE_{type_.value}",
            template_body=_VALID_BODIES[type_],
        )
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        yield seeds
    finally:
        app.dependency_overrides.clear()


def _create_payload(
    type_: str = "CODE_REVIEW",
    *,
    name: str = "C2-C review v2",
    body: str | None = None,
) -> dict:
    prompt_type = PromptType(type_)
    return {
        "type": type_,
        "name": name,
        "role_setting": "C2-C NEW ROLE",
        "template_body": body or _VALID_BODIES[prompt_type],
        "review_dimensions": "安全性,可维护性" if type_ == "CODE_REVIEW" else None,
        "severity_levels": "Critical,Warning,Info" if type_ == "CODE_REVIEW" else None,
    }


async def test_create_preview_and_rollback_are_append_only(client, db_session, c2c_context):
    v1 = c2c_context[PromptType.CODE_REVIEW]
    created = await client.post("/api/prompts", json=_create_payload())
    assert created.status_code == 200
    v2 = created.json()["data"]
    assert v2["version"] == v1.version + 1
    assert v2["is_active"] is True
    assert v2["template_body"] == _VALID_BODIES[PromptType.CODE_REVIEW]

    await db_session.refresh(v1)
    assert v1.is_active is False

    listed = await client.get("/api/prompts", params={"type": "CODE_REVIEW"})
    versions = listed.json()["data"]
    assert [item["version"] for item in versions[:2]] == [v2["version"], v1.version]

    preview = await client.get(
        f"/api/prompts/{v2['id']}/preview",
        params={"sample_code": "class C2CSample {}"},
    )
    assert preview.status_code == 200
    rendered = preview.json()["data"]["rendered"]
    assert "C2-C NEW ROLE" in rendered
    assert "class C2CSample {}" in rendered
    assert "{{source_code}}" not in rendered

    rollback = await client.post(f"/api/prompts/{v1.id}/activate")
    assert rollback.status_code == 200
    assert rollback.json()["data"]["is_active"] is True
    active_count = await db_session.scalar(
        select(func.count())
        .select_from(PromptTemplate)
        .where(
            PromptTemplate.type == "CODE_REVIEW",
            PromptTemplate.is_active.is_(True),
        )
    )
    assert active_count == 1
    assert await db_session.get(PromptTemplate, v2["id"]) is not None


@pytest.mark.parametrize(
    ("type_", "expected_fragments", "forbidden_fragment"),
    [
        ("CODE_REVIEW", ["class CanonicalSample {}"], "用户使用 FastAPI"),
        (
            "UNIT_TEST",
            ["src/Example.java", "JUnit5", "public int add"],
            "class CanonicalSample {}",
        ),
        (
            "AI_README",
            ["example-project", "[server-approved local snapshot]"],
            "class CanonicalSample {}",
        ),
        (
            "CHAT",
            ["用户使用 FastAPI", "项目采用 PostgreSQL", "请总结项目架构"],
            "class CanonicalSample {}",
        ),
    ],
)
async def test_preview_is_type_aware(
    client,
    c2c_context,
    type_,
    expected_fragments,
    forbidden_fragment,
):
    template = c2c_context[PromptType(type_)]
    response = await client.get(
        f"/api/prompts/{template.id}/preview",
        params={"sample_code": "class CanonicalSample {}"},
    )
    assert response.status_code == 200
    rendered = response.json()["data"]["rendered"]
    assert all(fragment in rendered for fragment in expected_fragments)
    assert forbidden_fragment not in rendered
    assert "{{" not in rendered


@pytest.mark.parametrize(
    ("payload", "status", "code"),
    [
        (
            {**_create_payload(), "type": "UNKNOWN"},
            422,
            "PROMPT_REQUEST_INVALID",
        ),
        (
            _create_payload(body="没有必需占位符"),
            400,
            "PROMPT_REQUIRED_PLACEHOLDERS_MISSING",
        ),
        (
            _create_payload(body="{{source_code}}\n{{unknown_context}}"),
            400,
            "PROMPT_UNKNOWN_PLACEHOLDER",
        ),
    ],
)
async def test_create_rejects_invalid_type_and_placeholders(
    client,
    c2c_context,
    payload,
    status,
    code,
):
    response = await client.post("/api/prompts", json=payload)
    assert response.status_code == status
    assert response.json() == {"code": 0, "msg": code, "data": None}


async def test_missing_preview_and_activation_use_stable_404(client, c2c_context):
    preview = await client.get("/api/prompts/999999/preview")
    activate = await client.post("/api/prompts/999999/activate")
    assert preview.status_code == activate.status_code == 404
    assert preview.json()["msg"] == activate.json()["msg"] == "PROMPT_NOT_FOUND"


async def test_concurrent_version_creation_and_activation_preserve_invariants(setup_db):
    prefix = "C2-C concurrent"

    async def create_version(index: int) -> int:
        async with AsyncSessionLocal() as session:
            service = PromptService(session, PromptTemplateManager(session))
            template = await service.create(
                PromptCreateRequest(
                    type=PromptType.CODE_REVIEW,
                    name=f"{prefix} {index}",
                    role_setting="concurrent role",
                    template_body="{{source_code}}",
                )
            )
            await session.commit()
            return template.id

    try:
        ids = await asyncio.gather(*(create_version(index) for index in range(3)))
        async with AsyncSessionLocal() as session:
            rows = list(
                (
                    await session.execute(
                        select(PromptTemplate)
                        .where(PromptTemplate.name.like(f"{prefix}%"))
                        .order_by(PromptTemplate.version)
                    )
                )
                .scalars()
                .all()
            )
            assert len(rows) == 3
            assert len({row.version for row in rows}) == 3
            assert [row.version for row in rows] == list(
                range(rows[0].version, rows[0].version + 3)
            )
            assert sum(row.is_active for row in rows) == 1

        async def activate(template_id: int) -> None:
            async with AsyncSessionLocal() as session:
                await PromptTemplateManager(session).activate(template_id)
                await session.commit()

        await asyncio.gather(activate(ids[0]), activate(ids[1]))
        async with AsyncSessionLocal() as session:
            active_count = await session.scalar(
                select(func.count())
                .select_from(PromptTemplate)
                .where(
                    PromptTemplate.type == "CODE_REVIEW",
                    PromptTemplate.is_active.is_(True),
                )
            )
            assert active_count == 1
    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(
                delete(PromptTemplate).where(PromptTemplate.name.like(f"{prefix}%"))
            )
            await session.commit()


async def test_c2c_demo_prompt_version_preview_rollback(client, c2c_context):
    v1 = c2c_context[PromptType.CHAT]
    created = await client.post(
        "/api/prompts",
        json=_create_payload(
            "CHAT",
            name="C2-C demo Chat v2",
        ),
    )
    v2 = created.json()["data"]
    preview = await client.get(f"/api/prompts/{v2['id']}/preview")
    rollback = await client.post(f"/api/prompts/{v1.id}/activate")
    assert created.status_code == preview.status_code == rollback.status_code == 200
    print(
        "C2-C demo:",
        {
            "created_version": v2["version"],
            "preview_resolved": "{{" not in preview.json()["data"]["rendered"],
            "rollback_version": rollback.json()["data"]["version"],
            "history_preserved": v2["id"] != v1.id,
        },
    )
