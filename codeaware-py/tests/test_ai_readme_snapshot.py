"""C1-E: safe local snapshot and route-level AIReadMe closure tests."""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path

import pytest
from sqlalchemy import delete, func, select, text

from app.ai.config import get_chat_model
from app.ai.prompt.template_manager import PromptTemplateManager
from app.ai.services.ai_readme import AiReadmeService
from app.ai.services.project_snapshot import (
    NON_REGULAR_FILE,
    PROJECT_OUTSIDE_ROOTS,
    SNAPSHOT_DISABLED,
    SNAPSHOT_EMPTY,
    SNAPSHOT_LIMIT_EXCEEDED,
    SYMLINK_NOT_ALLOWED,
    TRUNCATION_MARKER,
    ProjectSnapshotService,
)
from app.api.v1.ai_readme import get_project_snapshot_service
from app.core.enums import PromptType
from app.core.exceptions import BusinessException
from app.db.session import AsyncSessionLocal, get_db
from app.main import app
from conftest import clear_overrides_keep_auth  # noqa: E402
from app.models import AiReadmeDocument, PromptTemplate
from app.schemas.ai_readme import AiReadmeResult


def _snapshot_service(
    allowed_root: Path,
    *,
    enabled: bool = True,
    max_files: int = 20,
    max_file_bytes: int = 10_000,
    max_total_bytes: int = 50_000,
    max_prompt_chars: int = 20_000,
    timeout_seconds: float = 2,
) -> ProjectSnapshotService:
    return ProjectSnapshotService(
        enabled=enabled,
        allowed_roots=[allowed_root],
        max_files=max_files,
        max_file_bytes=max_file_bytes,
        max_total_bytes=max_total_bytes,
        max_prompt_chars=max_prompt_chars,
        timeout_seconds=timeout_seconds,
    )


def _write_fixture_project(root: Path, name: str = "fixture-repo") -> Path:
    project = root / name
    (project / "app").mkdir(parents=True)
    (project / "README.md").write_text(
        "# Fixture Repo\n\nA deterministic local project snapshot.\n",
        encoding="utf-8",
    )
    (project / "pyproject.toml").write_text(
        '[project]\nname = "fixture-repo"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    (project / "app" / "main.py").write_text(
        'def main() -> str:\n    return "fixture-entrypoint"\n',
        encoding="utf-8",
    )
    return project


class _StructuredInvoker:
    def __init__(
        self,
        owner: "_CapturingStructuredLLM",
        result: AiReadmeResult,
    ) -> None:
        self.owner = owner
        self.result = result

    async def ainvoke(self, prompt: str, **_kwargs):
        self.owner.prompts.append(prompt)
        if self.owner.delay_seconds:
            await asyncio.sleep(self.owner.delay_seconds)
        return self.result


class _CapturingStructuredLLM:
    def __init__(
        self,
        content: str = "# Generated README",
        *,
        delay_seconds: float = 0,
    ) -> None:
        self.result = AiReadmeResult(content=content)
        self.delay_seconds = delay_seconds
        self.prompts: list[str] = []

    def with_structured_output(self, _schema, **_kwargs):
        return _StructuredInvoker(self, self.result)

    async def ainvoke(self, _prompt, **_kwargs):
        raise AssertionError("valid structured output must not use the raw fallback")


class _AlwaysFailingLLM:
    def with_structured_output(self, _schema, **_kwargs):
        return self

    async def ainvoke(self, _prompt, **_kwargs):
        raise RuntimeError("synthetic LLM failure")


class _InvalidFallbackLLM:
    def with_structured_output(self, _schema, **_kwargs):
        return _FailingStructuredInvoker()

    async def ainvoke(self, _prompt, **_kwargs):
        class _Response:
            content = "not valid structured JSON"

        return _Response()


class _FailingStructuredInvoker:
    async def ainvoke(self, _prompt, **_kwargs):
        raise ValueError("synthetic structured-output failure")


class _TransactionBoundaryLLM:
    def __init__(self, session) -> None:
        self.session = session
        self.observed_transaction_free_invoke = False

    def with_structured_output(self, _schema, **_kwargs):
        return self

    async def ainvoke(self, _prompt, **_kwargs):
        assert self.session.in_transaction() is False
        self.observed_transaction_free_invoke = True
        return AiReadmeResult(content="# Transaction boundary verified")


async def _save_readme_template(session) -> PromptTemplate:
    return await PromptTemplateManager(session).save_and_activate(
        PromptType.AI_README,
        name="c1e-snapshot",
        role_setting="你是文档工程师",
        template_body="为 {{project_name}} 生成 README；输入={{project_path}}",
    )


def _override_ai_readme_dependencies(
    *,
    db_session,
    llm,
    snapshot_service: ProjectSnapshotService,
) -> None:
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_chat_model] = lambda: llm
    app.dependency_overrides[get_project_snapshot_service] = lambda: snapshot_service


async def test_snapshot_contains_real_files_and_excludes_sensitive_inputs(tmp_path):
    project = _write_fixture_project(tmp_path)
    (project / ".gitignore").write_text("ignored.py\nignored-dir/\n", encoding="utf-8")
    (project / ".env.production").write_text("TOKEN=do-not-leak\n", encoding="utf-8")
    (project / "server.pem").write_text("PRIVATE KEY do-not-leak\n", encoding="utf-8")
    (project / "ignored.py").write_text("IGNORED_SENTINEL = True\n", encoding="utf-8")
    (project / "ignored-dir").mkdir()
    (project / "ignored-dir" / "secret.py").write_text(
        "NESTED_IGNORED_SENTINEL = True\n",
        encoding="utf-8",
    )
    (project / "binary.py").write_bytes(b"\x00BINARY_SENTINEL")
    (project / "image.png").write_bytes(b"\x89PNG\r\n")
    (project / ".git").mkdir()
    (project / ".git" / "config").write_text("GIT_SECRET_SENTINEL\n", encoding="utf-8")
    (project / "node_modules").mkdir()
    (project / "node_modules" / "module.js").write_text(
        "NODE_MODULE_SENTINEL\n",
        encoding="utf-8",
    )

    snapshot = await _snapshot_service(tmp_path).build(str(project))
    payload = json.loads(snapshot.prompt_payload)
    file_paths = [item["path"] for item in payload["files"]]
    skipped = {(item.path, item.reason) for item in snapshot.skipped}

    assert file_paths == ["README.md", "pyproject.toml", "app/main.py"]
    assert "# Fixture Repo" in snapshot.prompt_payload
    assert "fixture-repo" in snapshot.prompt_payload
    assert "fixture-entrypoint" in snapshot.prompt_payload
    assert (".env.production", "denied") in skipped
    assert ("server.pem", "denied") in skipped
    assert ("ignored.py", "gitignored") in skipped
    assert ("ignored-dir", "gitignored") in skipped
    assert ("binary.py", "binary") in skipped
    assert (".git", "denied") in skipped
    assert ("node_modules", "denied") in skipped
    assert "do-not-leak" not in snapshot.prompt_payload
    assert "IGNORED_SENTINEL" not in snapshot.prompt_payload
    assert "BINARY_SENTINEL" not in snapshot.prompt_payload
    assert "GIT_SECRET_SENTINEL" not in snapshot.prompt_payload
    assert "NODE_MODULE_SENTINEL" not in snapshot.prompt_payload
    assert str(project) not in snapshot.prompt_payload


async def test_snapshot_hash_and_order_are_deterministic_and_content_sensitive(tmp_path):
    project = tmp_path / "stable-repo"
    (project / "src").mkdir(parents=True)
    # Create in reverse priority/alphabetic order to prove filesystem order is irrelevant.
    (project / "zeta.py").write_text("ZETA = 1\n", encoding="utf-8")
    (project / "src" / "index.ts").write_text("export const entry = 1;\n", encoding="utf-8")
    (project / "package.json").write_text('{"name":"stable"}\n', encoding="utf-8")
    (project / "README.md").write_text("# Stable\n", encoding="utf-8")
    service = _snapshot_service(tmp_path)

    first = await service.build(str(project))
    second = await service.build(str(project))
    first_payload = json.loads(first.prompt_payload)

    assert first.snapshot_hash == second.snapshot_hash
    assert first.prompt_payload == second.prompt_payload
    assert [item["kind"] for item in first_payload["files"]] == [
        "readme",
        "manifest",
        "entrypoint",
        "source",
    ]
    assert [item["path"] for item in first_payload["files"]] == [
        "README.md",
        "package.json",
        "src/index.ts",
        "zeta.py",
    ]

    (project / "zeta.py").write_text("ZETA = 2\n", encoding="utf-8")
    changed = await service.build(str(project))
    assert changed.snapshot_hash != first.snapshot_hash


async def test_prompt_budget_truncates_only_last_selected_file(tmp_path):
    project = tmp_path / "bounded-repo"
    project.mkdir()
    (project / "README.md").write_text("# Bounded\n" + ("R" * 220), encoding="utf-8")
    (project / "package.json").write_text("P" * 500, encoding="utf-8")
    (project / "main.py").write_text("M" * 500, encoding="utf-8")
    max_prompt_chars = 600

    snapshot = await _snapshot_service(
        tmp_path,
        max_prompt_chars=max_prompt_chars,
    ).build(str(project))
    payload = json.loads(snapshot.prompt_payload)

    assert len(snapshot.prompt_payload) <= max_prompt_chars
    assert snapshot.truncated is True
    assert payload["truncated"] is True
    assert payload["tree"] == ["main.py", "package.json", "README.md"]
    assert payload["files"][0]["path"] == "README.md"
    assert payload["files"][-1]["truncated"] is True
    assert payload["files"][-1]["content"].endswith(TRUNCATION_MARKER)
    assert sum(item["truncated"] for item in payload["files"]) == 1


@pytest.mark.parametrize(
    ("request_kind", "expected_error"),
    [
        ("relative", "AI_README_PROJECT_PATH_INVALID"),
        ("outside", PROJECT_OUTSIDE_ROOTS),
        ("root_symlink", SYMLINK_NOT_ALLOWED),
        ("nested_directory_symlink", SYMLINK_NOT_ALLOWED),
        ("nested_file_symlink", SYMLINK_NOT_ALLOWED),
        ("device", NON_REGULAR_FILE),
    ],
)
async def test_snapshot_rejects_unsafe_paths_and_non_regular_files(
    tmp_path,
    request_kind,
    expected_error,
):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    project = _write_fixture_project(allowed)
    requested = str(project)

    if request_kind == "relative":
        requested = "allowed/fixture-repo"
    elif request_kind == "outside":
        outside = _write_fixture_project(tmp_path, "outside")
        requested = str(allowed / ".." / outside.name)
    elif request_kind == "root_symlink":
        root_link = allowed / "root-link"
        root_link.symlink_to(project, target_is_directory=True)
        requested = str(root_link)
    elif request_kind == "nested_directory_symlink":
        (project / "linked-dir").symlink_to(
            tmp_path,
            target_is_directory=True,
        )
    elif request_kind == "nested_file_symlink":
        (project / "linked.py").symlink_to(project / "app" / "main.py")
    elif request_kind == "device":
        os.mkfifo(project / "device.py")

    with pytest.raises(BusinessException, match=expected_error):
        await _snapshot_service(allowed).build(requested)


async def test_disabled_snapshot_fails_closed_without_reading(tmp_path):
    project = _write_fixture_project(tmp_path)
    service = _snapshot_service(tmp_path, enabled=False)

    assert service.capability() == (False, "disabled")
    with pytest.raises(BusinessException, match=SNAPSHOT_DISABLED):
        await service.build(str(project))


async def test_capability_reports_missing_and_available_roots_without_paths(tmp_path):
    unavailable = _snapshot_service(tmp_path / "does-not-exist")
    available = _snapshot_service(tmp_path)

    assert unavailable.capability() == (False, "roots_unavailable")
    assert available.capability() == (True, "available")


@pytest.mark.parametrize("case", ["empty", "binary_only"])
async def test_empty_or_binary_only_project_fails_explicitly(tmp_path, case):
    project = tmp_path / case
    project.mkdir()
    if case == "binary_only":
        (project / "binary.py").write_bytes(b"\x00\x01\x02")

    with pytest.raises(BusinessException, match=SNAPSHOT_EMPTY):
        await _snapshot_service(tmp_path).build(str(project))


@pytest.mark.parametrize(
    ("limit", "service_kwargs"),
    [
        ("file_count", {"max_files": 1}),
        ("file_bytes", {"max_file_bytes": 8}),
        ("total_bytes", {"max_total_bytes": 20}),
    ],
)
async def test_snapshot_hard_limits_fail_explicitly(tmp_path, limit, service_kwargs):
    project = tmp_path / f"limit-{limit}"
    project.mkdir()
    (project / "README.md").write_text("# Readme body\n", encoding="utf-8")
    (project / "main.py").write_text("print('second file')\n", encoding="utf-8")

    with pytest.raises(BusinessException, match=SNAPSHOT_LIMIT_EXCEEDED):
        await _snapshot_service(tmp_path, **service_kwargs).build(str(project))


async def test_snapshot_timeout_fails_as_limit_without_partial_result(tmp_path, monkeypatch):
    project = _write_fixture_project(tmp_path)
    service = _snapshot_service(tmp_path, timeout_seconds=0.01)
    original_build = service._build_sync

    def _slow_build(project_path: str):
        time.sleep(0.05)
        return original_build(project_path)

    monkeypatch.setattr(service, "_build_sync", _slow_build)
    with pytest.raises(BusinessException, match=SNAPSHOT_LIMIT_EXCEEDED):
        await service.build(str(project))


@pytest.mark.parametrize("llm", [_AlwaysFailingLLM(), _InvalidFallbackLLM()])
async def test_llm_failure_or_invalid_output_does_not_write_record(
    db_session,
    tmp_path,
    llm,
):
    await _save_readme_template(db_session)
    project = _write_fixture_project(tmp_path)
    service = AiReadmeService(
        db_session,
        llm,
        PromptTemplateManager(db_session),
        _snapshot_service(tmp_path),
    )

    from app.core.exceptions import BusinessException

    with pytest.raises(BusinessException) as raised:
        await service.generate("failed-readme", str(project))
    assert raised.value.message == "AI_README_OUTPUT_INVALID"

    count = await db_session.scalar(
        select(func.count(AiReadmeDocument.id)).where(
            AiReadmeDocument.project_name == "failed-readme"
        )
    )
    assert count == 0


async def test_capabilities_route_has_only_public_state(client, db_session, tmp_path):
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        scenarios = [
            (_snapshot_service(tmp_path, enabled=False), False, "disabled"),
            (
                _snapshot_service(tmp_path / "missing-root"),
                False,
                "roots_unavailable",
            ),
            (_snapshot_service(tmp_path), True, "available"),
        ]
        for snapshot_service, expected_enabled, expected_reason in scenarios:
            app.dependency_overrides[get_project_snapshot_service] = (
                lambda service=snapshot_service: service
            )
            response = await client.get("/api/ai-readme/capabilities")
            assert response.status_code == 200
            assert response.json()["data"] == {
                "enabled": expected_enabled,
                "reason": expected_reason,
            }
            assert str(tmp_path) not in response.text
    finally:
        clear_overrides_keep_auth()


async def test_generate_route_rejects_outside_path_without_leaking_it(
    client,
    db_session,
    tmp_path,
):
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    (outside / "README.md").write_text("# outside\n", encoding="utf-8")
    _override_ai_readme_dependencies(
        db_session=db_session,
        llm=_CapturingStructuredLLM(),
        snapshot_service=_snapshot_service(allowed),
    )
    try:
        response = await client.post(
            "/api/ai-readme/generate",
            json={"project_name": "outside", "project_path": str(outside)},
        )
        assert response.status_code == 400
        assert response.json()["msg"] == PROJECT_OUTSIDE_ROOTS
        assert str(outside) not in response.text
    finally:
        clear_overrides_keep_auth()


async def test_generate_route_validation_redacts_oversized_absolute_path(
    client,
    db_session,
    tmp_path,
):
    sensitive_marker = "C1E_PRIVATE_ABSOLUTE_PATH_SEGMENT"
    oversized_path = "/" + (f"{sensitive_marker}/" * 220)
    _override_ai_readme_dependencies(
        db_session=db_session,
        llm=_CapturingStructuredLLM(),
        snapshot_service=_snapshot_service(tmp_path),
    )
    try:
        response = await client.post(
            "/api/ai-readme/generate",
            json={
                "project_name": "validation-redaction",
                "project_path": oversized_path,
            },
        )
    finally:
        clear_overrides_keep_auth()

    assert response.status_code == 422
    assert response.json() == {
        "code": 0,
        "msg": "AI_README_REQUEST_INVALID",
        "data": None,
    }
    assert oversized_path not in response.text
    assert sensitive_marker not in response.text


async def test_concurrent_generation_serializes_project_versions(setup_db, tmp_path):
    """Separate sessions prove the PostgreSQL advisory lock prevents duplicate versions."""
    project_name = "c1e-concurrent-version"
    project = _write_fixture_project(tmp_path)
    template_id: int | None = None
    try:
        async with AsyncSessionLocal() as seed_session:
            template = await _save_readme_template(seed_session)
            template_id = template.id
            await seed_session.commit()

        async def _generate(content: str) -> int:
            async with AsyncSessionLocal() as session:
                service = AiReadmeService(
                    session,
                    _CapturingStructuredLLM(content, delay_seconds=0.02),
                    PromptTemplateManager(session),
                    _snapshot_service(tmp_path),
                )
                generated = await service.generate(project_name, str(project))
                await session.commit()
                return generated.version

        versions = await asyncio.gather(
            _generate("# Concurrent A"),
            _generate("# Concurrent B"),
        )
        assert sorted(versions) == [1, 2]

        async with AsyncSessionLocal() as verify_session:
            persisted = list(
                (
                    await verify_session.scalars(
                        select(AiReadmeDocument)
                        .where(AiReadmeDocument.project_name == project_name)
                        .order_by(AiReadmeDocument.version)
                    )
                ).all()
            )
            assert [record.version for record in persisted] == [1, 2]
    finally:
        async with AsyncSessionLocal() as cleanup_session:
            await cleanup_session.execute(
                delete(AiReadmeDocument).where(
                    AiReadmeDocument.project_name == project_name
                )
            )
            if template_id is not None:
                await cleanup_session.execute(
                    delete(PromptTemplate).where(PromptTemplate.id == template_id)
                )
            await cleanup_session.commit()


async def test_llm_runs_outside_transaction_then_advisory_write_commits(
    setup_db,
    tmp_path,
):
    project_name = "c1e-transaction-boundary"
    project = _write_fixture_project(tmp_path)
    template_id: int | None = None
    try:
        async with AsyncSessionLocal() as seed_session:
            template = await _save_readme_template(seed_session)
            template_id = template.id
            await seed_session.commit()

        async with AsyncSessionLocal() as session:
            assert session.in_transaction() is False
            llm = _TransactionBoundaryLLM(session)
            service = AiReadmeService(
                session,
                llm,
                PromptTemplateManager(session),
                _snapshot_service(tmp_path),
            )

            generated = await service.generate(project_name, str(project))

            assert llm.observed_transaction_free_invoke is True
            assert session.in_transaction() is True
            advisory_locks = await session.scalar(
                text(
                    "SELECT count(*) FROM pg_locks "
                    "WHERE locktype = 'advisory' "
                    "AND pid = pg_backend_pid() "
                    "AND granted"
                )
            )
            assert advisory_locks == 1
            await session.commit()
            assert session.in_transaction() is False

        async with AsyncSessionLocal() as verify_session:
            persisted = await verify_session.scalar(
                select(AiReadmeDocument).where(
                    AiReadmeDocument.project_name == project_name,
                    AiReadmeDocument.version == generated.version,
                )
            )
            assert persisted is not None
            assert persisted.content == "# Transaction boundary verified"
    finally:
        async with AsyncSessionLocal() as cleanup_session:
            await cleanup_session.execute(
                delete(AiReadmeDocument).where(
                    AiReadmeDocument.project_name == project_name
                )
            )
            if template_id is not None:
                await cleanup_session.execute(
                    delete(PromptTemplate).where(PromptTemplate.id == template_id)
                )
            await cleanup_session.commit()


async def test_c1e_demo_route_snapshot_versions_latest_and_rejections(
    client,
    db_session,
    tmp_path,
):
    """Deterministic route-level closure used by ``-k c1e_demo -s``."""
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    project = _write_fixture_project(allowed)
    (project / ".gitignore").write_text("ignored.py\n", encoding="utf-8")
    (project / "ignored.py").write_text("IGNORED = True\n", encoding="utf-8")
    (project / ".env").write_text("SECRET=never\n", encoding="utf-8")
    (project / "binary.py").write_bytes(b"\x00binary")
    outside = _write_fixture_project(tmp_path, "outside")
    symlink = allowed / "project-link"
    symlink.symlink_to(project, target_is_directory=True)

    await _save_readme_template(db_session)
    llm = _CapturingStructuredLLM("# Generated from fixture snapshot")
    snapshot_service = _snapshot_service(allowed)
    _override_ai_readme_dependencies(
        db_session=db_session,
        llm=llm,
        snapshot_service=snapshot_service,
    )
    try:
        payload = {"project_name": "fixture-demo", "project_path": str(project)}
        first_response = await client.post("/api/ai-readme/generate", json=payload)
        second_response = await client.post("/api/ai-readme/generate", json=payload)
        latest_response = await client.get("/api/ai-readme/fixture-demo")
        outside_response = await client.post(
            "/api/ai-readme/generate",
            json={"project_name": "rejected-outside", "project_path": str(outside)},
        )
        symlink_response = await client.post(
            "/api/ai-readme/generate",
            json={"project_name": "rejected-symlink", "project_path": str(symlink)},
        )
    finally:
        clear_overrides_keep_auth()

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert latest_response.status_code == 200
    first = first_response.json()["data"]
    second = second_response.json()["data"]
    latest = latest_response.json()["data"]
    assert [first["version"], second["version"]] == [1, 2]
    assert first["snapshot_hash"] == second["snapshot_hash"]
    assert latest["version"] == 2
    assert latest["id"] == second["id"]
    assert latest["snapshot_hash"] == second["snapshot_hash"]
    assert len(llm.prompts) == 2
    assert all("# Fixture Repo" in prompt for prompt in llm.prompts)
    assert all("fixture-repo" in prompt for prompt in llm.prompts)
    assert all("fixture-entrypoint" in prompt for prompt in llm.prompts)
    assert all("不可信资料" in prompt for prompt in llm.prompts)
    assert all("<project_snapshot" in prompt for prompt in llm.prompts)
    assert all(str(project) not in prompt for prompt in llm.prompts)
    assert all("IGNORED = True" not in prompt for prompt in llm.prompts)
    assert all("SECRET=never" not in prompt for prompt in llm.prompts)
    assert outside_response.status_code == 400
    assert outside_response.json()["msg"] == PROJECT_OUTSIDE_ROOTS
    assert symlink_response.status_code == 400
    assert symlink_response.json()["msg"] == SYMLINK_NOT_ALLOWED

    persisted = list(
        (
            await db_session.scalars(
                select(AiReadmeDocument)
                .where(
                    AiReadmeDocument.project_name.in_(
                        ["fixture-demo", "rejected-outside", "rejected-symlink"]
                    )
                )
                .order_by(AiReadmeDocument.version)
            )
        ).all()
    )
    assert [(record.project_name, record.version) for record in persisted] == [
        ("fixture-demo", 1),
        ("fixture-demo", 2),
    ]

    snapshot = await snapshot_service.build(str(project))
    relative_files = [item.path for item in snapshot.files]
    excluded = [(item.path, item.reason) for item in snapshot.skipped]
    print(f"[C1-E DEMO] relative_files={relative_files}")
    print(f"[C1-E DEMO] excluded={excluded}")
    print(
        "[C1-E DEMO] prompt_contains="
        f"README:{'# Fixture Repo' in llm.prompts[0]},"
        f"manifest:{'fixture-repo' in llm.prompts[0]}"
    )
    print(
        f"[C1-E DEMO] versions={first['version']}/{second['version']} "
        f"same_hash={first['snapshot_hash'] == second['snapshot_hash']}"
    )
    print(
        f"[C1-E DEMO] latest_version={latest['version']} "
        f"latest_id={latest['id']}"
    )
    print(
        "[C1-E DEMO] rejected="
        f"outside:{outside_response.json()['msg']},"
        f"symlink:{symlink_response.json()['msg']}"
    )
    print(f"[C1-E DEMO] successful_records={len(persisted)}")
