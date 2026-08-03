#!/usr/bin/env python3
"""Validate the only machine-readable stage evidence entrypoint."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

STAGE_PROFILE = {
    "C1": "current-release",
    "C2": "current-release",
    "C3": "current-release",
    "C4": "current-release",
    "S1": "personal-local-readonly",
    "S2": "personal-local-readonly",
    "S4": "personal-local-readonly",
    "S5": "personal-local-readonly",
}
DAG = {
    "C1": [],
    "C2": ["C1"],
    "C3": ["C2"],
    "C4": ["C3"],
    "S1": ["C4"],
    "S2": ["S1"],
    "S4": ["S2"],
    "S5": ["S4"],
}
REQUIRED_CHECKS = {
    "C1": ["C1-SAFE-HARNESS", "C1-A", "C1-B", "C1-C", "C1-D", "C1-E"],
    "C2": ["code-review", "unit-test", "ai-readme", "chat", "knowledge", "memory", "prompt"],
    "C3": ["fresh-bootstrap", "docs-contract", "rollback", "freeze-handoff"],
    "C4": [
        "bm25-runtime",
        "lexical-quality",
        "hybrid-fusion",
        "index-lifecycle",
        "fallback-rollback",
    ],
    "S1": ["migration-scope", "api-scope", "retrieval-isolation", "frontend-scope", "rollback"],
    "S2": ["behavior-parity", "architecture-boundary", "uow-transaction", "rollback"],
    "S4": [
        "tool-governance",
        "budget-loop",
        "citation-persistence",
        "chat-runtime-regression",
        "security-negative",
        "rollback",
    ],
    "S5": [
        "repository-provenance",
        "scanner-security",
        "index-idempotency",
        "tool-citation",
        "source-unchanged",
        "profile-safety-locks",
        "rollback",
    ],
}
REQUIRED_KEYS = [
    "schema_version",
    "stage",
    "route_profile",
    "run_id",
    "baseline_commit",
    "implementation_commit",
    "implementation_parent",
    "validated_head",
    "supersedes_manifest_sha256",
    "dependencies",
    "authorization",
    "report",
    "environment",
    "migration",
    "openapi",
    "commands",
    "checks",
    "rollback",
    "limitations",
    "result",
]
REQUIRED_COMMAND_KEYS = {
    "id",
    "argv",
    "cwd",
    "exit_code",
    "started_at",
    "finished_at",
    "stdout",
    "sha256",
    "required",
}
C1_REQUIRED_COMMANDS = {
    "dependency-lock",
    "compose-config",
    "c1-total-demo",
    "backend-full",
    "backend-coverage",
    "frontend-test",
    "frontend-lint",
    "frontend-build",
    "rollback",
}
C2_REQUIRED_COMMANDS = {
    "dependency-lock",
    "compose-config",
    "c2-mocked-demo",
    "backend-full",
    "backend-coverage",
    "api-e2e",
    "frontend-install",
    "frontend-test",
    "frontend-lint",
    "frontend-build",
    "browser-e2e",
    "live-smoke",
    "rollback",
}
C2_COMMAND_CONTRACTS = {
    "dependency-lock": ("codeaware-py", ["uv", "lock", "--check"]),
    "compose-config": (".", ["docker", "compose", "config", "--quiet"]),
    "c2-mocked-demo": (
        ".",
        ["./codeaware-py/scripts/demo_c2_mocked.sh"],
    ),
    "backend-full": (
        "codeaware-py",
        ["uv", "run", "python", "scripts/run_tests_safe.py", "-q"],
    ),
    "backend-coverage": (
        "codeaware-py",
        [
            "uv",
            "run",
            "python",
            "scripts/run_tests_safe.py",
            "--cov=app",
            "--cov-report=term-missing",
            "-q",
        ],
    ),
    "api-e2e": (
        "codeaware-py",
        [
            "uv",
            "run",
            "python",
            "scripts/run_tests_safe.py",
            "tests/contracts",
            "tests/e2e",
            "-q",
        ],
    ),
    "frontend-install": ("codeaware-py/frontend", ["npm", "ci"]),
    "frontend-test": ("codeaware-py/frontend", ["npm", "run", "test"]),
    "frontend-lint": ("codeaware-py/frontend", ["npm", "run", "lint"]),
    "frontend-build": ("codeaware-py/frontend", ["npm", "run", "build"]),
    "browser-e2e": (
        "codeaware-py",
        [
            "uv",
            "run",
            "python",
            "scripts/run_tests_safe.py",
            "--browser-e2e",
        ],
    ),
    "live-smoke": (".", ["./codeaware-py/scripts/demo_c2_live.sh"]),
    "rollback": (".", ["./codeaware-py/scripts/verify_c2_rollback.sh"]),
}
C3_COMMAND_CONTRACTS = {
    "current-release-verify": (
        ".",
        ["./codeaware-py/scripts/verify_current_release.sh"],
    ),
    "handoff-demo": (
        ".",
        ["./codeaware-py/scripts/demo_c3_handoff.sh"],
    ),
    "rollback": (
        ".",
        ["./codeaware-py/scripts/verify_c3_rollback.sh"],
    ),
}
C3_REQUIRED_COMMANDS = set(C3_COMMAND_CONTRACTS)
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
RUN_ID_PATTERN = re.compile(r"^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$")
SENSITIVE_TEXT_PATTERNS = (
    re.compile(r"(?i)\b(?:postgresql|redis)://\S+"),
    re.compile(r"(?i)\b(?:LLM_API_KEY|PG_PASSWORD|CODEWARE_TEST_AUTH)\s*="),
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}"),
    re.compile(r"(?:^|[\s\"'])/(?:Users|home)/[^/\s\"']+/"),
)


def manifest_path_for(stage: str) -> Path:
    profile = STAGE_PROFILE[stage]
    subdir = "current-release" if profile == "current-release" else "chat-to-agent"
    return REPO_ROOT / "docs" / "roadmap" / subdir / "evidence" / stage / "manifest.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args],
        capture_output=True,
        text=True,
    )


def _is_ancestor(ancestor: str, descendant: str) -> bool:
    return _git(["merge-base", "--is-ancestor", ancestor, descendant]).returncode == 0


def _validate_hashed_file(
    manifest_dir: Path,
    artifact: Any,
    label: str,
    errors: list[str],
) -> None:
    if not isinstance(artifact, dict):
        errors.append(f"{label} 必须是带 path/sha256 的对象")
        return
    rel = artifact.get("path")
    expected = artifact.get("sha256")
    if not isinstance(rel, str) or not rel or not isinstance(expected, str) or not expected:
        errors.append(f"{label} 缺 path/sha256")
        return
    path = (manifest_dir / rel).resolve()
    try:
        path.relative_to(manifest_dir.resolve())
    except ValueError:
        errors.append(f"{label} 路径逃逸: {rel}")
        return
    if not SHA256_PATTERN.fullmatch(expected):
        errors.append(f"{label} sha256 格式错误")
        return
    if not path.is_file():
        errors.append(f"{label} 不存在: {rel}")
    elif sha256_file(path) != expected:
        errors.append(f"{label} sha256 不符")
    else:
        _validate_artifact_text(path, label, errors)


def _validate_artifact_text(path: Path, label: str, errors: list[str]) -> None:
    if path.suffix.lower() not in {".json", ".log", ".md", ".txt"}:
        return
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        errors.append(f"{label} 不是可读 UTF-8 文本")
        return
    repo_root_text = str(REPO_ROOT.resolve())
    if repo_root_text and repo_root_text in content:
        errors.append(f"{label} 含仓库绝对路径")
    for pattern in SENSITIVE_TEXT_PATTERNS:
        if pattern.search(content):
            errors.append(f"{label} 含宿主路径、凭据或完整连接串")
            break


def _validate_repo_cwd(cwd: Any, label: str, errors: list[str]) -> None:
    if not isinstance(cwd, str) or not cwd:
        errors.append(f"{label} cwd 缺失")
        return
    path = (REPO_ROOT / cwd).resolve()
    try:
        path.relative_to(REPO_ROOT.resolve())
    except ValueError:
        errors.append(f"{label} cwd 路径逃逸: {cwd}")
        return
    if not path.is_dir():
        errors.append(f"{label} cwd 不存在: {cwd}")


def _artifact_text(
    manifest_dir: Path,
    relative_path: Any,
) -> str:
    if not isinstance(relative_path, str):
        return ""
    path = (manifest_dir / relative_path).resolve()
    try:
        path.relative_to(manifest_dir.resolve())
    except ValueError:
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _parse_rfc3339(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _validate_commit(value: Any, label: str, errors: list[str]) -> None:
    if not isinstance(value, str) or not COMMIT_PATTERN.fullmatch(value):
        errors.append(f"{label} 必须是 40 位 commit")
        return
    if _git(["cat-file", "-e", f"{value}^{{commit}}"]).returncode != 0:
        errors.append(f"{label} commit 不存在: {value}")


def _validate_environment(environment: Any, errors: list[str]) -> None:
    if not isinstance(environment, dict):
        errors.append("environment 必须是对象")
        return
    if environment.get("mode") != "disposable":
        errors.append("environment.mode 必须为 disposable")
    database = environment.get("postgres_database")
    if not isinstance(database, str) or not database.startswith("codeaware_test_"):
        errors.append("environment.postgres_database 必须是一次性 codeaware_test_*")
    redis_database = environment.get("redis_database")
    if not isinstance(redis_database, int) or redis_database == 0:
        errors.append("environment.redis_database 必须是非 0 整数")
    if environment.get("sandbox_or_compose_profile") != "test":
        errors.append("environment.sandbox_or_compose_profile 必须为 test")


def _validate_migration(
    stage: str,
    migration: Any,
    manifest_dir: Path,
    errors: list[str],
) -> None:
    if not isinstance(migration, dict):
        errors.append("migration 必须是对象")
        return
    heads = migration.get("heads")
    current = migration.get("current")
    expected_head = {
        "C1": "0004",
        "C2": "0005",
        "C3": "0005",
        "C4": "0006",
    }.get(stage, "0005")
    if heads != [expected_head] or current != [expected_head] or heads != current:
        errors.append(
            "migration heads/current 必须唯一且均为 "
            f"['{expected_head}']"
        )
    artifact = {
        "path": migration.get("log"),
        "sha256": migration.get("sha256"),
    }
    _validate_hashed_file(manifest_dir, artifact, "migration.log", errors)
    path = manifest_dir / str(migration.get("log", ""))
    if path.is_file():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            errors.append("migration.log 必须是 JSON")
        else:
            if payload.get("heads") != heads or payload.get("current") != current:
                errors.append("migration.log 与 manifest heads/current 不一致")


def _validate_rollback(
    rollback: Any,
    manifest_dir: Path,
    errors: list[str],
) -> None:
    if not isinstance(rollback, dict):
        errors.append("rollback 必须是对象")
        return
    if rollback.get("temp_worktree") is not True:
        errors.append("rollback.temp_worktree 必须为 true")
    if rollback.get("disposable_database") is not True:
        errors.append("rollback.disposable_database 必须为 true")
    if rollback.get("result") != "passed":
        errors.append("rollback 未通过")
    _validate_hashed_file(
        manifest_dir,
        {
            "path": rollback.get("artifact"),
            "sha256": rollback.get("sha256"),
        },
        "rollback.artifact",
        errors,
    )


def validate(stage: str, manifest: dict, manifest_dir: Path) -> list[str]:
    errors: list[str] = []

    if stage not in STAGE_PROFILE:
        return [f"未知 stage: {stage}"]
    if not isinstance(manifest, dict):
        return ["manifest 必须是 JSON object"]
    for key in REQUIRED_KEYS:
        if key not in manifest:
            errors.append(f"缺字段: {key}")
    if manifest.get("schema_version") != 1:
        errors.append("schema_version 必须为 1")
    if not isinstance(manifest.get("run_id"), str) or not RUN_ID_PATTERN.fullmatch(
        manifest.get("run_id", "")
    ):
        errors.append("run_id 格式必须为 YYYYMMDDTHHMMSSZ-8hex")
    supersedes = manifest.get("supersedes_manifest_sha256")
    if supersedes is not None and (
        not isinstance(supersedes, str) or not SHA256_PATTERN.fullmatch(supersedes)
    ):
        errors.append("supersedes_manifest_sha256 必须为 null 或 SHA-256")
    if not isinstance(manifest.get("limitations"), list):
        errors.append("limitations 必须是数组")

    if manifest.get("stage") != stage:
        errors.append(f"stage 不匹配: manifest={manifest.get('stage')!r} arg={stage!r}")
    expected_profile = STAGE_PROFILE[stage]
    if manifest.get("route_profile") != expected_profile:
        errors.append(
            f"route_profile 应为 {expected_profile!r}, 实为 {manifest.get('route_profile')!r}"
        )

    deps = manifest.get("dependencies")
    if not isinstance(deps, list):
        errors.append("dependencies 必须是数组")
        deps = []
    dep_stages = sorted(
        dep.get("stage") for dep in deps if isinstance(dep, dict) and dep.get("stage")
    )
    legal = sorted(DAG[stage])
    if dep_stages != legal:
        errors.append(f"依赖不符: manifest={dep_stages} 合法={legal}")
    for dependency in deps:
        if not isinstance(dependency, dict):
            errors.append("dependency 必须是对象")
            continue
        dep_stage = dependency.get("stage")
        if dep_stage not in STAGE_PROFILE:
            errors.append(f"未知依赖阶段: {dep_stage!r}")
            continue
        if not dependency.get("manifest_sha256") or not dependency.get("validated_commit"):
            errors.append(f"依赖 {dep_stage} 缺 manifest_sha256/validated_commit")
        dep_path = manifest_path_for(dep_stage)
        if not dep_path.exists():
            errors.append(f"依赖 {dep_stage} manifest 不存在: {dep_path}")
            continue
        if dependency.get("manifest_sha256") != sha256_file(dep_path):
            errors.append(f"依赖 {dep_stage} manifest sha256 不符")
        try:
            dep_manifest = json.loads(dep_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            errors.append(f"依赖 {dep_stage} manifest JSON 解析失败")
            continue
        if dep_manifest.get("result") != "passed":
            errors.append(f"依赖 {dep_stage} result={dep_manifest.get('result')} (应 passed)")
        if dependency.get("validated_commit") != dep_manifest.get("validated_head"):
            errors.append(f"依赖 {dep_stage} validated_commit 与 manifest 不一致")

    implementation = manifest.get("implementation_commit")
    baseline = manifest.get("baseline_commit")
    parent = manifest.get("implementation_parent")
    head = manifest.get("validated_head")
    _validate_commit(baseline, "baseline_commit", errors)
    _validate_commit(implementation, "implementation_commit", errors)
    _validate_commit(parent, "implementation_parent", errors)
    _validate_commit(head, "validated_head", errors)
    if baseline and implementation and not _is_ancestor(baseline, implementation):
        errors.append(f"baseline {baseline} 不是 implementation {implementation} 的祖先")
    if parent and implementation:
        actual_parent = _git(["rev-parse", f"{implementation}^"]).stdout.strip()
        if actual_parent != parent:
            errors.append(f"implementation_parent {parent} != 实际父 {actual_parent}")
    if implementation and head and not _is_ancestor(implementation, head):
        errors.append(f"implementation {implementation} 不在 validated_head {head} 祖先链")
    if stage.startswith("C") and manifest.get("authorization") is not None:
        errors.append(f"{stage} authorization 必须为 null")

    report = manifest.get("report")
    if not isinstance(report, dict) or report.get("path") != "report.md":
        errors.append("report.path 必须为 report.md")
    _validate_hashed_file(manifest_dir, report, "report", errors)
    _validate_environment(manifest.get("environment"), errors)
    _validate_migration(stage, manifest.get("migration"), manifest_dir, errors)
    _validate_hashed_file(
        manifest_dir,
        manifest.get("openapi"),
        "openapi",
        errors,
    )

    commands = manifest.get("commands")
    if not isinstance(commands, list) or not commands:
        errors.append("commands 必须是非空数组")
        commands = []
    command_ids: set[str] = set()
    for command in commands:
        if not isinstance(command, dict):
            errors.append("command 必须是对象")
            continue
        command_id = command.get("id", "?")
        missing = sorted(REQUIRED_COMMAND_KEYS - command.keys())
        if command.get("required") and missing:
            errors.append(f"命令 {command_id} 缺字段: {', '.join(missing)}")
        if command_id in command_ids:
            errors.append(f"命令 id 重复: {command_id}")
        command_ids.add(command_id)
        if command.get("required") and command.get("exit_code") != 0:
            errors.append(f"命令 {command_id} exit_code={command.get('exit_code')} (应 0)")
        if command.get("required") and not isinstance(command.get("argv"), list):
            errors.append(f"命令 {command_id} argv 必须是数组")
        started = _parse_rfc3339(command.get("started_at"))
        finished = _parse_rfc3339(command.get("finished_at"))
        if started is None or finished is None or finished < started:
            errors.append(f"命令 {command_id} 时间格式或顺序错误")
        _validate_repo_cwd(command.get("cwd"), f"命令 {command_id}", errors)
        _validate_hashed_file(
            manifest_dir,
            {"path": command.get("stdout"), "sha256": command.get("sha256")},
            f"命令 {command_id} stdout",
            errors,
        )
    if stage == "C1" and command_ids != C1_REQUIRED_COMMANDS:
        errors.append(
            "C1 commands 必须精确为 "
            f"{sorted(C1_REQUIRED_COMMANDS)}，实为 {sorted(command_ids)}"
        )
    if stage == "C2":
        if command_ids != C2_REQUIRED_COMMANDS:
            errors.append(
                "C2 commands 必须精确为 "
                f"{sorted(C2_REQUIRED_COMMANDS)}，实为 {sorted(command_ids)}"
            )
        command_map = {
            command.get("id"): command
            for command in commands
            if isinstance(command, dict)
        }
        for command_id, (expected_cwd, expected_argv) in C2_COMMAND_CONTRACTS.items():
            command = command_map.get(command_id)
            if command is None:
                continue
            if command.get("cwd") != expected_cwd:
                errors.append(
                    f"C2 命令 {command_id} cwd 必须为 {expected_cwd!r}"
                )
            if command.get("argv") != expected_argv:
                errors.append(
                    f"C2 命令 {command_id} argv 与冻结契约不一致"
                )

        required_markers = {
            "c2-mocked-demo": [
                "[PASS] Code Review",
                "[PASS] Unit Test",
                "[PASS] AIReadMe",
                "[PASS] Chat",
                "[PASS] Knowledge",
                "[PASS] Memory",
                "[PASS] Prompt",
                "[C2 MOCKED] PASS",
            ],
            "backend-full": ["passed, 2 deselected", "exact cleanup complete"],
            "browser-e2e": ["7 passed", "exact cleanup complete"],
            "live-smoke": [
                '"dimension": 1024',
                '"real_llm_calls": 3',
                "[C2 LIVE] PASS",
                "exact cleanup complete",
            ],
            "rollback": ["[C2 ROLLBACK] PASS"],
        }
        for command_id, markers in required_markers.items():
            command = command_map.get(command_id)
            if command is None:
                continue
            output = _artifact_text(manifest_dir, command.get("stdout"))
            for marker in markers:
                if marker not in output:
                    errors.append(
                        f"C2 命令 {command_id} 日志缺少标记: {marker}"
                    )
    if stage == "C3":
        if command_ids != C3_REQUIRED_COMMANDS:
            errors.append(
                "C3 commands 必须精确为 "
                f"{sorted(C3_REQUIRED_COMMANDS)}，实为 {sorted(command_ids)}"
            )
        command_map = {
            command.get("id"): command
            for command in commands
            if isinstance(command, dict)
        }
        for command_id, (expected_cwd, expected_argv) in C3_COMMAND_CONTRACTS.items():
            command = command_map.get(command_id)
            if command is None:
                continue
            if command.get("cwd") != expected_cwd:
                errors.append(
                    f"C3 命令 {command_id} cwd 必须为 {expected_cwd!r}"
                )
            if command.get("argv") != expected_argv:
                errors.append(
                    f"C3 命令 {command_id} argv 与冻结契约不一致"
                )
        required_markers = {
            "current-release-verify": [
                "[C3 VERIFY] PASS fresh-bootstrap exit=0",
                "[C3 VERIFY] PASS backend-full exit=0",
                "[C3 VERIFY] PASS backend-coverage exit=0",
                "[C3 VERIFY] PASS release-metrics exit=0",
                "[C3 VERIFY] PASS browser-e2e exit=0",
                "[C3 VERIFY] PASS release=0.1.0",
                "repository_status_unchanged=true",
                "development_resources_unchanged=true",
            ],
            "handoff-demo": [
                "[C3 METRICS]",
                "[PASS] Code Review",
                "[PASS] Prompt",
                "[C3 HANDOFF] PASS C2 committed live-smoke evidence hash revalidated",
                "[C3 HANDOFF] PASS repository_status_unchanged=true",
            ],
            "rollback": [
                "[C3 BACKUP] PASS",
                "[C3 ROLLBACK] PASS worktree_removed=true",
                "backup_restore=true",
                "main_unchanged=true",
            ],
        }
        for command_id, markers in required_markers.items():
            command = command_map.get(command_id)
            if command is None:
                continue
            output = _artifact_text(manifest_dir, command.get("stdout"))
            for marker in markers:
                if marker not in output:
                    errors.append(
                        f"C3 命令 {command_id} 日志缺少标记: {marker}"
                    )

        expected_gate = {
            "current_release_complete": True,
            "agent_review_allowed": False,
            "agent_implementation_authorized": False,
            "next_stage": "C4",
            "default_route_profile": "personal-local-readonly",
        }
        if manifest.get("gate") != expected_gate:
            errors.append("C3 gate 必须精确锁定 Agent 并只解锁 C4")

    checks = manifest.get("checks")
    if not isinstance(checks, list):
        errors.append("checks 必须是数组")
        checks = []
    check_map: dict[str, dict] = {}
    for check in checks:
        if not isinstance(check, dict):
            errors.append("check 必须是对象")
            continue
        check_id = check.get("id")
        if check_id in check_map:
            errors.append(f"check id 重复: {check_id}")
        check_map[check_id] = check
    expected_checks = set(REQUIRED_CHECKS[stage])
    if set(check_map) != expected_checks:
        errors.append(
            f"checks 必须精确为 {sorted(expected_checks)}，实为 {sorted(check_map)}"
        )
    for required_check in REQUIRED_CHECKS[stage]:
        check = check_map.get(required_check)
        if check is None:
            errors.append(f"缺 required check: {required_check}")
            continue
        if check.get("status") != "passed":
            errors.append(f"check {required_check} 状态={check.get('status')} (应 passed)")
        artifacts = check.get("artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            errors.append(f"check {required_check} 必须引用至少一个 artifact")
            continue
        for index, artifact in enumerate(artifacts):
            _validate_hashed_file(
                manifest_dir,
                artifact,
                f"check {required_check} artifact[{index}]",
                errors,
            )

    _validate_rollback(manifest.get("rollback"), manifest_dir, errors)
    if manifest.get("result") != "passed":
        errors.append(f"result={manifest.get('result')!r} (应 'passed')")
    return errors


def validate_evidence_commit(
    manifest_path: Path,
    manifest: dict,
) -> list[str]:
    """Require the current manifest contents to be committed after validated_head."""
    errors: list[str] = []
    relative = manifest_path.relative_to(REPO_ROOT).as_posix()
    status = _git(["status", "--porcelain=v1", "--", relative])
    if status.returncode != 0 or status.stdout.strip():
        errors.append("manifest 必须先提交，且不能有未提交修改")
        return errors
    evidence_commit = _git(["log", "-1", "--format=%H", "--", relative])
    commit = evidence_commit.stdout.strip()
    if evidence_commit.returncode != 0 or not COMMIT_PATTERN.fullmatch(commit):
        errors.append("无法定位当前 manifest 的 evidence commit")
        return errors
    if not _is_ancestor(commit, "HEAD"):
        errors.append("evidence commit 不在当前 HEAD 祖先链")
    parent = _git(["rev-parse", f"{commit}^"]).stdout.strip()
    validated_head = manifest.get("validated_head")
    if not isinstance(validated_head, str) or not _is_ancestor(validated_head, parent):
        errors.append("evidence commit 的父链不包含 validated_head")
    return errors


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in STAGE_PROFILE:
        print(f"用法: validate_stage_evidence.py <{'|'.join(STAGE_PROFILE)}>", file=sys.stderr)
        print(
            f"未知 stage: {sys.argv[1] if len(sys.argv) > 1 else '(无)'}",
            file=sys.stderr,
        )
        return 2
    stage = sys.argv[1]
    manifest_path = manifest_path_for(stage)
    if not manifest_path.exists():
        print(f"✗ manifest 不存在: {manifest_path}", file=sys.stderr)
        return 1
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"✗ manifest JSON 解析失败: {exc}", file=sys.stderr)
        return 1
    errors = validate(stage, manifest, manifest_path.parent)
    errors.extend(validate_evidence_commit(manifest_path, manifest))
    if errors:
        print(
            f"✗ stage {stage} ({STAGE_PROFILE[stage]}) manifest 校验失败 "
            f"({len(errors)} 项):",
            file=sys.stderr,
        )
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print(f"✓ stage {stage} ({STAGE_PROFILE[stage]}) manifest 校验通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
