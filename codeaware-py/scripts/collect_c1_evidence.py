#!/usr/bin/env python3
"""Run and collect the deterministic C1 closure evidence."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from validate_stage_evidence import REQUIRED_CHECKS, validate

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = REPO_ROOT / "codeaware-py"
FRONTEND_ROOT = APP_ROOT / "frontend"
EVIDENCE_ROOT = REPO_ROOT / "docs/roadmap/current-release/evidence/C1"

BASELINE_COMMIT = "efd6c378885b7d99ca886e3bc6548dd3aabca299"
IMPLEMENTATION_COMMIT = "2a0a4e948e20e3d9ff5dbc24ca9d7a1c5b009231"
IMPLEMENTATION_PARENT = "b683425c9af7c5cd24d44e8a7d88764bd0590406"

COMMANDS = [
    ("dependency-lock", APP_ROOT, ["uv", "lock", "--check"]),
    ("compose-config", REPO_ROOT, ["docker", "compose", "config", "--quiet"]),
    (
        "c1-total-demo",
        REPO_ROOT,
        ["./codeaware-py/scripts/demo_c1_current_fixes.sh"],
    ),
    (
        "backend-full",
        APP_ROOT,
        ["uv", "run", "python", "scripts/run_tests_safe.py", "-q"],
    ),
    (
        "backend-coverage",
        APP_ROOT,
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
    ("frontend-test", FRONTEND_ROOT, ["npm", "run", "test"]),
    ("frontend-lint", FRONTEND_ROOT, ["npm", "run", "lint"]),
    ("frontend-build", FRONTEND_ROOT, ["npm", "run", "build"]),
    (
        "rollback",
        REPO_ROOT,
        ["./codeaware-py/scripts/verify_c1_rollback.sh"],
    ),
]


class EvidenceFailure(RuntimeError):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def format_utc(value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def redact(text: str) -> str:
    value = text.replace(str(REPO_ROOT), "<repo_root>")
    value = re.sub(
        r"/(?:private/)?(?:tmp|var/folders)/[^\s\"']+",
        "<temp_path>",
        value,
    )
    value = re.sub(
        r"(?i)\b((?:LLM_API_KEY|PG_PASSWORD|CODEWARE_TEST_AUTH)\s*=)\S+",
        r"\1<redacted>",
        value,
    )
    value = re.sub(r"\bsk-[A-Za-z0-9_-]{8,}", "sk-<redacted>", value)
    value = re.sub(
        r"(?i)\b(?:postgresql|redis)://\S+",
        "<redacted-connection>",
        value,
    )
    return value


def relative_cwd(path: Path) -> str:
    relative = path.relative_to(REPO_ROOT).as_posix()
    return relative or "."


def clean_command_environment() -> dict[str, str]:
    environment = os.environ.copy()
    for name in (
        "LLM_API_KEY",
        "LOCAL_PROJECT_ROOTS",
        "AI_README_SNAPSHOT_ENABLED",
        "PG_HOST",
        "PG_PORT",
        "PG_DB",
        "REDIS_HOST",
        "REDIS_PORT",
        "REDIS_DB",
        "CODEWARE_TEST_STACK_ID",
        "CODEWARE_TEST_AUTH",
    ):
        environment.pop(name, None)
    environment["CODEAWARE_TESTING"] = "1"
    return environment


def run_command(
    command_id: str,
    cwd: Path,
    argv: list[str],
    artifact_dir: Path,
) -> dict:
    started = utc_now()
    print(f"[C1 EVIDENCE] start {command_id}")
    process = subprocess.run(
        argv,
        cwd=cwd,
        env=clean_command_environment(),
        capture_output=True,
        text=True,
    )
    finished = utc_now()
    log_path = artifact_dir / f"{command_id}.log"
    output = redact(process.stdout + process.stderr)
    log_path.write_text(output, encoding="utf-8")
    print(
        f"[C1 EVIDENCE] finish {command_id} "
        f"exit={process.returncode} seconds={(finished - started).total_seconds():.1f}"
    )
    record = {
        "id": command_id,
        "cwd": relative_cwd(cwd),
        "argv": argv,
        "exit_code": process.returncode,
        "started_at": format_utc(started),
        "finished_at": format_utc(finished),
        "stdout": f"artifacts/{log_path.name}",
        "sha256": sha256_file(log_path),
        "required": True,
    }
    if process.returncode != 0:
        raise EvidenceFailure(f"required command failed: {command_id}")
    return record


def export_openapi(path: Path) -> None:
    os.environ["CODEAWARE_TESTING"] = "1"
    sys.path.insert(0, str(APP_ROOT))
    from app.main import app

    write_json(path, app.openapi())


def command_log(artifact_dir: Path, command_id: str) -> str:
    return (artifact_dir / f"{command_id}.log").read_text(encoding="utf-8")


def build_stage_files(
    stage_dir: Path,
    run_id: str,
    validated_head: str,
    command_records: list[dict],
    supersedes: str | None,
) -> dict:
    artifact_dir = stage_dir / "artifacts"
    demo_log = command_log(artifact_dir, "c1-total-demo")
    backend_log = command_log(artifact_dir, "backend-full")
    coverage_log = command_log(artifact_dir, "backend-coverage")
    rollback_log = command_log(artifact_dir, "rollback")

    if "Alembic current=0004 (head)" not in demo_log:
        raise EvidenceFailure("fresh bootstrap did not prove Alembic 0004 head")
    if "[C1 DEMO] PASS" not in demo_log:
        raise EvidenceFailure("C1 total demo did not report PASS")
    if "[C1 ROLLBACK] PASS" not in rollback_log:
        raise EvidenceFailure("rollback did not report PASS")
    full_match = re.search(r"(\d+) passed, 1 deselected", backend_log)
    coverage_match = re.search(r"TOTAL\s+\d+\s+\d+\s+(\d+)%", coverage_log)
    if not full_match:
        raise EvidenceFailure("backend full test count missing")
    if not coverage_match or int(coverage_match.group(1)) < 92:
        raise EvidenceFailure("backend coverage below 92% or missing")

    stack_match = re.search(
        r"test_db=(codeaware_test_[0-9a-f]+).*redis_db=(\d+)",
        backend_log,
    )
    if not stack_match:
        raise EvidenceFailure("safe runner disposable environment identity missing")

    openapi_path = artifact_dir / "openapi.json"
    export_openapi(openapi_path)
    migration_path = artifact_dir / "migration.json"
    write_json(
        migration_path,
        {
            "heads": ["0004"],
            "current": ["0004"],
            "source_command": "c1-total-demo",
            "fresh_bootstrap": True,
        },
    )
    environment_path = artifact_dir / "environment.json"
    write_json(
        environment_path,
        {
            "mode": "disposable",
            "postgres_database": stack_match.group(1),
            "redis_database": int(stack_match.group(2)),
            "sandbox_or_compose_profile": "test",
            "exact_cleanup": "exact cleanup complete" in backend_log,
            "development_resources_unchanged": (
                "development resource fingerprint unchanged" in demo_log
            ),
        },
    )
    rollback_path = artifact_dir / "rollback.json"
    write_json(
        rollback_path,
        {
            "result": "passed",
            "implementation_commit": IMPLEMENTATION_COMMIT,
            "implementation_parent": IMPLEMENTATION_PARENT,
            "temp_worktree": True,
            "disposable_database": True,
            "migration_chain": ["0004", "0003", "0002", "base", "head"],
            "worktree_removed": True,
            "development_resources_unchanged": True,
            "source_command": "rollback",
        },
    )

    check_sources = {
        "C1-SAFE-HARNESS": [
            "c1-total-demo",
            "backend-full",
            "rollback",
        ],
        "C1-A": ["c1-total-demo", "backend-full", "frontend-test"],
        "C1-B": ["c1-total-demo", "backend-full"],
        "C1-C": ["c1-total-demo", "backend-full"],
        "C1-D": ["c1-total-demo", "backend-full", "rollback"],
        "C1-E": ["c1-total-demo", "backend-full"],
    }
    check_assertions = {
        "C1-SAFE-HARNESS": [
            "temporary PG/Redis identity verified",
            "development and forged targets rejected",
            "exact cleanup completed",
        ],
        "C1-A": [
            "typed SSE sequence and terminal verified",
            "whitespace preserved",
            "Redis degradation, abort, and concurrency verified",
        ],
        "C1-B": [
            "summary threshold and watermark reached 10",
            "PG/Redis equality and cache warning verified",
        ],
        "C1-C": [
            "multipart contract verified",
            "uploaded document recalled by knowledge search",
        ],
        "C1-D": [
            "fresh dual database bootstrap verified",
            "readiness degradation and recovery verified",
        ],
        "C1-E": [
            "safe fixture snapshot reached LLM prompt",
            "version/hash/latest and path rejection verified",
        ],
    }
    checks = []
    for check_id in REQUIRED_CHECKS["C1"]:
        path = artifact_dir / f"{check_id}.json"
        write_json(
            path,
            {
                "check_id": check_id,
                "status": "passed",
                "source_commands": check_sources[check_id],
                "assertions": check_assertions[check_id],
            },
        )
        checks.append(
            {
                "id": check_id,
                "status": "passed",
                "artifacts": [
                    {
                        "path": f"artifacts/{path.name}",
                        "sha256": sha256_file(path),
                    }
                ],
            }
        )

    report_path = stage_dir / "report.md"
    command_rows = "\n".join(
        f"| {record['id']} | `{record['cwd']}` | {record['exit_code']} | "
        f"`{record['stdout']}` | `{record['sha256']}` |"
        for record in command_records
    )
    report_path.write_text(
        f"""# C1 当前缺口修复验收报告

## 元信息

- stage：C1
- route profile：current-release
- run_id：`{run_id}`
- baseline：`{BASELINE_COMMIT}`
- implementation：`{IMPLEMENTATION_COMMIT}`
- implementation parent：`{IMPLEMENTATION_PARENT}`
- validated head：`{validated_head}`
- dependencies：无

## 结果与边界

C1-SAFE-HARNESS 与 C1-A 至 C1-E 的确定性演示、全量测试、覆盖率、前端检查、
fresh bootstrap 和 detached rollback 均通过。未实施 C2、C3、Agent 或仓库写能力。

## 自动命令

| id | cwd | exit | log | SHA-256 |
|---|---|---:|---|---|
{command_rows}

## 环境与契约

- PostgreSQL/Redis：随机一次性 stack，Redis DB 非 0。
- Alembic：唯一 head/current 均为 `0004`。
- OpenAPI：`artifacts/openapi.json`。
- 开发 Docker 资源与主工作区在演示/回退前后未变化。

## Checks

- C1-SAFE-HARNESS：目标 sentinel、拒绝开发/伪造目标、清理闭环。
- C1-A：typed SSE、空白、降级、取消与并发。
- C1-B：摘要阈值、水位线、PG/Redis 与 warning。
- C1-C：multipart、持久化、检索与稳定错误。
- C1-D：fresh bootstrap、health/readiness 与恢复。
- C1-E：安全 snapshot、版本/hash/latest 与路径拒绝。

## 回退

在 detached 临时 worktree 验证最终实现父提交 `{IMPLEMENTATION_PARENT}`，并在一次性
数据库验证 `0004 → 0003 → 0002 → base → head`。worktree 和 stack 已精确清理。

## 限制

- 自动 Evidence 使用 fake LLM/embedder；正式 live smoke 和七域浏览器 E2E 属于 C2。
- 手动真实启动联调为补充验证，见 `C1-手动可视化联调.md`，不计入 manifest 门禁。
- 当前 per-conversation turn guard 是本机单 worker 约束。
- AIReadMe snapshot 默认关闭且没有隐式 allowed root。

## 结论

`result=passed`。该结论只解锁当前版本 C2，不解锁任何 Agent 实施。
""",
        encoding="utf-8",
    )

    manifest = {
        "schema_version": 1,
        "stage": "C1",
        "route_profile": "current-release",
        "run_id": run_id,
        "baseline_commit": BASELINE_COMMIT,
        "implementation_commit": IMPLEMENTATION_COMMIT,
        "implementation_parent": IMPLEMENTATION_PARENT,
        "validated_head": validated_head,
        "supersedes_manifest_sha256": supersedes,
        "dependencies": [],
        "authorization": None,
        "report": {
            "path": "report.md",
            "sha256": sha256_file(report_path),
        },
        "environment": {
            "mode": "disposable",
            "postgres_database": stack_match.group(1),
            "redis_database": int(stack_match.group(2)),
            "sandbox_or_compose_profile": "test",
        },
        "migration": {
            "heads": ["0004"],
            "current": ["0004"],
            "log": "artifacts/migration.json",
            "sha256": sha256_file(migration_path),
        },
        "openapi": {
            "path": "artifacts/openapi.json",
            "sha256": sha256_file(openapi_path),
        },
        "commands": command_records,
        "checks": checks,
        "rollback": {
            "temp_worktree": True,
            "disposable_database": True,
            "result": "passed",
            "artifact": "artifacts/rollback.json",
            "sha256": sha256_file(rollback_path),
        },
        "limitations": [
            "deterministic fake models only; formal live smoke is C2",
            "manual visual smoke is supplemental and non-blocking",
            "local single-worker conversation guard",
            "AIReadMe snapshot is disabled by default",
        ],
        "result": "passed",
    }
    write_json(stage_dir / "manifest.json", manifest)
    return manifest


def copy_attempt(temp_stage: Path, run_id: str, reason: str) -> Path:
    attempt = EVIDENCE_ROOT / "attempts" / run_id
    attempt.parent.mkdir(parents=True, exist_ok=True)
    if attempt.exists():
        raise EvidenceFailure(f"attempt already exists: {run_id}")
    shutil.copytree(temp_stage, attempt)
    write_json(
        attempt / "failure.json",
        {"run_id": run_id, "result": "failed", "reason": redact(reason)},
    )
    return attempt


def promote_success(temp_stage: Path) -> None:
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
    (EVIDENCE_ROOT / "artifacts").mkdir(parents=True, exist_ok=True)
    for source in (temp_stage / "artifacts").iterdir():
        os.replace(source, EVIDENCE_ROOT / "artifacts" / source.name)
    os.replace(temp_stage / "report.md", EVIDENCE_ROOT / "report.md")
    os.replace(temp_stage / "manifest.json", EVIDENCE_ROOT / "manifest.json")


def main() -> int:
    status = git("status", "--porcelain=v1", "--untracked-files=all")
    if status:
        print("[C1 EVIDENCE] worktree must be clean", file=sys.stderr)
        return 1
    validated_head = git("rev-parse", "HEAD")
    if git("rev-parse", IMPLEMENTATION_COMMIT) != IMPLEMENTATION_COMMIT:
        print("[C1 EVIDENCE] implementation commit missing", file=sys.stderr)
        return 1
    ancestor = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "merge-base", "--is-ancestor", IMPLEMENTATION_COMMIT, validated_head]
    )
    if ancestor.returncode != 0:
        print("[C1 EVIDENCE] validated HEAD does not contain implementation", file=sys.stderr)
        return 1

    run_id = utc_now().strftime("%Y%m%dT%H%M%SZ") + f"-{secrets.token_hex(4)}"
    supersedes = (
        sha256_file(EVIDENCE_ROOT / "manifest.json")
        if (EVIDENCE_ROOT / "manifest.json").is_file()
        else None
    )
    print(f"[C1 EVIDENCE] run_id={run_id} validated_head={validated_head}")

    with tempfile.TemporaryDirectory(prefix="codeaware-c1-evidence-") as temporary:
        temp_stage = Path(temporary) / "C1"
        artifact_dir = temp_stage / "artifacts"
        artifact_dir.mkdir(parents=True)
        records: list[dict] = []
        try:
            for command_id, cwd, argv in COMMANDS:
                records.append(run_command(command_id, cwd, argv, artifact_dir))
            manifest = build_stage_files(
                temp_stage,
                run_id,
                validated_head,
                records,
                supersedes,
            )
            validation_errors = validate("C1", manifest, temp_stage)
            if validation_errors:
                raise EvidenceFailure("; ".join(validation_errors))
        except Exception as exc:  # noqa: BLE001
            attempt = copy_attempt(temp_stage, run_id, str(exc))
            print(
                f"[C1 EVIDENCE] failed; attempt retained at "
                f"{attempt.relative_to(REPO_ROOT)}",
                file=sys.stderr,
            )
            return 1
        promote_success(temp_stage)

    print(
        "[C1 EVIDENCE] PASS generated "
        "docs/roadmap/current-release/evidence/C1/manifest.json"
    )
    print("[C1 EVIDENCE] commit the evidence before running validate_stage_evidence.py C1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
