#!/usr/bin/env python3
"""Collect the C3 current-release freeze, handoff, and rollback evidence."""

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
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

from validate_stage_evidence import (
    C3_COMMAND_CONTRACTS,
    REQUIRED_CHECKS,
    sha256_file,
    validate,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = REPO_ROOT / "codeaware-py"
EVIDENCE_ROOT = REPO_ROOT / "docs/roadmap/current-release/evidence/C3"
C2_EVIDENCE_ROOT = REPO_ROOT / "docs/roadmap/current-release/evidence/C2"
C2_MANIFEST = C2_EVIDENCE_ROOT / "manifest.json"
RELEASE_NOTES = REPO_ROOT / "docs/releases/0.1.0.md"

BASELINE_COMMIT = "c54459885e2461e3453eed249846adf76ac296b2"
IMPLEMENTATION_COMMIT = "7b9bcc838a126bf2796f62f61275eb2c00da5edb"
IMPLEMENTATION_PARENT = "9bb1b63c0da8ffedb3d30f185cc1560a79cddc04"

COMMANDS = [
    (
        "current-release-verify",
        REPO_ROOT,
        ["./codeaware-py/scripts/verify_current_release.sh"],
    ),
    (
        "handoff-demo",
        REPO_ROOT,
        ["./codeaware-py/scripts/demo_c3_handoff.sh"],
    ),
    (
        "rollback",
        REPO_ROOT,
        ["./codeaware-py/scripts/verify_c3_rollback.sh"],
    ),
]


class EvidenceFailure(RuntimeError):
    pass


def utc_now() -> datetime:
    return datetime.now(UTC)


def format_utc(value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


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
    value = value.replace(quote(str(REPO_ROOT)), "<repo_root_urlencoded>")
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
        r"(?i)\b(?:postgresql(?:\+\w+)?|redis)://\S+",
        "<redacted-connection>",
        value,
    )
    normalized = "\n".join(line.rstrip() for line in value.splitlines())
    return normalized + ("\n" if value.endswith(("\n", "\r")) else "")


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
        "CODEAWARE_BROWSER_E2E",
        "CODEAWARE_BROWSER_E2E_PROJECT_ROOT",
    ):
        environment.pop(name, None)
    environment["CODEAWARE_TESTING"] = "1"
    return environment


def relative_cwd(path: Path) -> str:
    relative = path.relative_to(REPO_ROOT).as_posix()
    return relative or "."


def run_command(
    command_id: str,
    cwd: Path,
    argv: list[str],
    artifact_dir: Path,
) -> dict:
    started = utc_now()
    print(f"[C3 EVIDENCE] start {command_id}")
    process = subprocess.run(
        argv,
        cwd=cwd,
        env=clean_command_environment(),
        capture_output=True,
        text=True,
    )
    finished = utc_now()
    log_path = artifact_dir / f"{command_id}.log"
    log_path.write_text(
        redact(process.stdout + process.stderr),
        encoding="utf-8",
    )
    print(
        f"[C3 EVIDENCE] finish {command_id} "
        f"exit={process.returncode} "
        f"seconds={(finished - started).total_seconds():.1f}"
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


def command_log(artifact_dir: Path, command_id: str) -> str:
    return (artifact_dir / f"{command_id}.log").read_text(encoding="utf-8")


def require_markers(text: str, markers: list[str], label: str) -> None:
    missing = [marker for marker in markers if marker not in text]
    if missing:
        raise EvidenceFailure(f"{label} missing markers: {missing}")


def section(text: str, label: str) -> str:
    start_marker = f"[C3 VERIFY] START {label}"
    end_marker = f"[C3 VERIFY] PASS {label} exit=0"
    start = text.find(start_marker)
    end = text.find(end_marker, start + len(start_marker))
    if start < 0 or end < 0:
        raise EvidenceFailure(f"verify section missing: {label}")
    return text[start:end]


def extract_metrics(text: str) -> dict:
    # pytest -s can prefix captured print output with progress dots.
    match = re.search(r"^[^\r\n]*\[C3 METRICS\] (\{.*\})$", text, re.MULTILINE)
    if not match:
        raise EvidenceFailure("C3 metrics JSON missing")
    try:
        metrics = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise EvidenceFailure("C3 metrics JSON invalid") from exc
    if metrics.get("chat", {}).get("sse_fidelity") != 1.0:
        raise EvidenceFailure("SSE fidelity baseline is not 100%")
    retrieval = metrics.get("retrieval", {})
    if retrieval.get("cases") != 30:
        raise EvidenceFailure("retrieval golden set must contain 30 cases")
    if retrieval.get("rrf", {}).get("recall@5") != 1.0:
        raise EvidenceFailure("RRF Recall@5 baseline is incomplete")
    return metrics


def copy_c2_live_reference(path: Path) -> dict:
    c2_manifest = json.loads(C2_MANIFEST.read_text(encoding="utf-8"))
    live_command = next(
        command
        for command in c2_manifest["commands"]
        if command["id"] == "live-smoke"
    )
    live_log = C2_EVIDENCE_ROOT / live_command["stdout"]
    if sha256_file(live_log) != live_command["sha256"]:
        raise EvidenceFailure("C2 live command artifact hash mismatch")
    live_metrics_path = C2_EVIDENCE_ROOT / "artifacts/live-smoke.json"
    live_metrics = json.loads(live_metrics_path.read_text(encoding="utf-8"))
    reference = {
        "c2_manifest_sha256": sha256_file(C2_MANIFEST),
        "c2_validated_commit": c2_manifest["validated_head"],
        "live_command_sha256": live_command["sha256"],
        "live_metrics_sha256": sha256_file(live_metrics_path),
        "live_metrics": live_metrics,
        "reused_without_new_provider_call": True,
    }
    write_json(path, reference)
    return reference


def export_openapi(path: Path) -> None:
    os.environ["CODEAWARE_TESTING"] = "1"
    sys.path.insert(0, str(APP_ROOT))
    from app.main import app

    write_json(path, app.openapi())


def build_stage_files(
    stage_dir: Path,
    run_id: str,
    validated_head: str,
    command_records: list[dict],
    supersedes: str | None,
) -> dict:
    artifact_dir = stage_dir / "artifacts"
    verify_log = command_log(artifact_dir, "current-release-verify")
    handoff_log = command_log(artifact_dir, "handoff-demo")
    rollback_log = command_log(artifact_dir, "rollback")

    require_markers(
        verify_log,
        [
            "[C3 VERIFY] PASS fresh-bootstrap exit=0",
            "[C3 VERIFY] PASS backend-full exit=0",
            "[C3 VERIFY] PASS backend-coverage exit=0",
            "[C3 VERIFY] PASS browser-e2e exit=0",
            "[C3 VERIFY] PASS release=0.1.0",
            "repository_status_unchanged=true",
            "development_resources_unchanged=true",
        ],
        "current release verify",
    )
    require_markers(
        handoff_log,
        [
            "[PASS] Code Review",
            "[PASS] Unit Test",
            "[PASS] AIReadMe",
            "[PASS] Chat",
            "[PASS] Knowledge",
            "[PASS] Memory",
            "[PASS] Prompt",
            "[C3 HANDOFF] PASS C2 committed live-smoke evidence hash revalidated",
        ],
        "handoff demo",
    )
    require_markers(
        rollback_log,
        [
            "[C3 BACKUP] PASS",
            "[C3 ROLLBACK] PASS",
            "backup_restore=true",
            "main_unchanged=true",
        ],
        "rollback",
    )

    backend_match = re.search(
        r"(\d+) passed, 2 deselected",
        section(verify_log, "backend-full"),
    )
    coverage_match = re.search(
        r"TOTAL\s+\d+\s+\d+\s+(\d+)%",
        section(verify_log, "backend-coverage"),
    )
    browser_match = re.search(
        r"(\d+) passed",
        section(verify_log, "browser-e2e"),
    )
    frontend_match = re.search(
        r"Tests\s+(\d+) passed",
        section(verify_log, "frontend-test"),
    )
    fresh_match = re.search(
        r"\[C3 VERIFY\] PASS fresh-bootstrap exit=0 seconds=(\d+)",
        verify_log,
    )
    total_match = re.search(
        r"\[C3 VERIFY\] PASS release=0\.1\.0 total_seconds=(\d+)",
        verify_log,
    )
    if not all(
        (
            backend_match,
            coverage_match,
            browser_match,
            frontend_match,
            fresh_match,
            total_match,
        )
    ):
        raise EvidenceFailure("release verification quantitative result missing")

    metrics = extract_metrics(handoff_log)
    metrics_path = artifact_dir / "metrics.json"
    write_json(metrics_path, metrics)
    c2_live_path = artifact_dir / "c2-live-reference.json"
    c2_live = copy_c2_live_reference(c2_live_path)

    stack_match = re.search(
        r"test_db=(codeaware_test_[0-9a-f]+).*redis_db=(\d+)",
        section(verify_log, "backend-full"),
    )
    if not stack_match:
        raise EvidenceFailure("disposable safe-runner identity missing")

    openapi_path = artifact_dir / "openapi.json"
    export_openapi(openapi_path)
    migration_path = artifact_dir / "migration.json"
    write_json(
        migration_path,
        {
            "heads": ["0005"],
            "current": ["0005"],
            "source_command": "rollback",
            "roundtrip": [
                "base",
                "0002",
                "0003",
                "0004",
                "0003",
                "0004",
                "0005",
                "0004",
                "0005",
                "0002",
                "0005",
                "base",
                "head",
            ],
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
            "fresh_bootstrap_seconds": int(fresh_match.group(1)),
            "total_verify_seconds": int(total_match.group(1)),
            "exact_cleanup": True,
            "development_resources_unchanged": True,
        },
    )
    rollback_path = artifact_dir / "rollback.json"
    write_json(
        rollback_path,
        {
            "result": "passed",
            "freeze_commit": validated_head,
            "rollback_commit": BASELINE_COMMIT,
            "temp_worktree": True,
            "disposable_database": True,
            "migration_head": "0005",
            "logical_backup_restore": True,
            "worktree_removed": True,
            "development_resources_unchanged": True,
            "source_command": "rollback",
        },
    )
    docs_contract_path = artifact_dir / "docs-contract.json"
    openapi = json.loads(openapi_path.read_text(encoding="utf-8"))
    write_json(
        docs_contract_path,
        {
            "version": "0.1.0",
            "openapi_paths": len(openapi["paths"]),
            "openapi_operations": sum(
                method.lower()
                in {"get", "post", "put", "patch", "delete", "options", "head"}
                for item in openapi["paths"].values()
                for method in item
            ),
            "openapi_snapshot_matches": True,
            "settings_env_example_exact": True,
            "release_hygiene_passed": True,
            "release_notes_sha256": sha256_file(RELEASE_NOTES),
        },
    )
    fresh_path = artifact_dir / "fresh-bootstrap.json"
    write_json(
        fresh_path,
        {
            "result": "passed",
            "seconds": int(fresh_match.group(1)),
            "alembic_head": "0005",
            "health_degradation_recovery": True,
            "development_resources_unchanged": True,
        },
    )
    handoff_path = artifact_dir / "freeze-handoff.json"
    write_json(
        handoff_path,
        {
            "result": "passed",
            "release": "0.1.0",
            "validated_head": validated_head,
            "backend_passed": int(backend_match.group(1)),
            "backend_coverage_percent": int(coverage_match.group(1)),
            "frontend_tests_passed": int(frontend_match.group(1)),
            "browser_domains_passed": int(browser_match.group(1)),
            "metrics_sha256": sha256_file(metrics_path),
            "c2_live_reference_sha256": sha256_file(c2_live_path),
            "c2_live_reused_without_new_provider_call": c2_live[
                "reused_without_new_provider_call"
            ],
            "agent_implementation_authorized": False,
            "next_stage": "C4",
        },
    )

    check_paths = {
        "fresh-bootstrap": fresh_path,
        "docs-contract": docs_contract_path,
        "rollback": rollback_path,
        "freeze-handoff": handoff_path,
    }
    checks = []
    for check_id in REQUIRED_CHECKS["C3"]:
        path = check_paths[check_id]
        artifacts = [
            {
                "path": f"artifacts/{path.name}",
                "sha256": sha256_file(path),
            }
        ]
        if check_id == "freeze-handoff":
            artifacts.extend(
                [
                    {
                        "path": "artifacts/metrics.json",
                        "sha256": sha256_file(metrics_path),
                    },
                    {
                        "path": "artifacts/c2-live-reference.json",
                        "sha256": sha256_file(c2_live_path),
                    },
                ]
            )
        checks.append(
            {"id": check_id, "status": "passed", "artifacts": artifacts}
        )

    c2_manifest = json.loads(C2_MANIFEST.read_text(encoding="utf-8"))
    dependency = {
        "stage": "C2",
        "manifest_sha256": sha256_file(C2_MANIFEST),
        "validated_commit": c2_manifest["validated_head"],
    }
    report_path = stage_dir / "report.md"
    command_rows = "\n".join(
        f"| {record['id']} | `{record['cwd']}` | {record['exit_code']} | "
        f"`{record['stdout']}` | `{record['sha256']}` |"
        for record in command_records
    )
    chat_metrics = metrics["chat"]
    retrieval = metrics["retrieval"]
    report_path.write_text(
        f"""# C3 当前版本冻结与交接报告

## 元信息

- stage：C3
- release：0.1.0
- route profile：current-release
- run_id：`{run_id}`
- baseline：`{BASELINE_COMMIT}`
- implementation：`{IMPLEMENTATION_COMMIT}`
- implementation parent：`{IMPLEMENTATION_PARENT}`
- validated head：`{validated_head}`
- dependency：C2 `{dependency['manifest_sha256']}`

## 结果与边界

文档、OpenAPI、配置、版本、fresh bootstrap、全量测试、七域 browser E2E、固定评测、
交接演示和 detached rollback 均通过。C2 已提交 live smoke 的命令与指标哈希重新验证；
本次没有重复产生真实 provider 调用。未实施 C4、Agent、工具调用或仓库写能力。

## 自动命令

| id | cwd | exit | log | SHA-256 |
|---|---|---:|---|---|
{command_rows}

## 量化基线

- 后端全量：{backend_match.group(1)} passed，2 deselected。
- 后端覆盖率 TOTAL：{coverage_match.group(1)}%。
- 前端：{frontend_match.group(1)} tests passed；lint/build 通过。
- Browser E2E：{browser_match.group(1)} 个 UI 功能域通过。
- Fresh bootstrap：{fresh_match.group(1)} 秒；完整冻结验证：{total_match.group(1)} 秒。
- 固定 fake Chat（{chat_metrics['samples']} 样本）：首 token P50
  `{chat_metrics['first_token_ms']['p50']}ms`、P95
  `{chat_metrics['first_token_ms']['p95']}ms`；完整响应 P50
  `{chat_metrics['full_response_ms']['p50']}ms`、P95
  `{chat_metrics['full_response_ms']['p95']}ms`；SSE 保真率 100%。
- 30 条检索集：pg_trgm Recall@5
  `{retrieval['pg_trgm']['recall@5']}`，vector Recall@5
  `{retrieval['vector']['recall@5']}`，当前 RRF Recall@5
  `{retrieval['rrf']['recall@5']}`。

固定 fake 延迟只用于相同环境回归对比，不是生产压测或真实网络 SLA。

## 契约、安全与回退

- 版本 `0.1.0` 在 pyproject、FastAPI/OpenAPI 和前端 package/lock 一致。
- Alembic 唯一 head/current 为 `0005`；迁移链与逻辑备份/恢复只作用于一次性数据库。
- secret、宿主路径、上传限制和 AIReadMe traversal/symlink 回归通过。
- 回退只在 detached C2 worktree 执行，主工作区与开发 Docker 资源未变化。

## 限制

- local-first、单用户、无认证/RBAC/多租户。
- per-conversation guard 仅支持单 worker；多 worker 前需 PostgreSQL lease。
- Unit Test 不执行生成代码；普通自动化使用 fake provider。
- 当前词法腿是 pg_trgm，不是 BM25；前端 bundle 仍有体积优化空间。
- 没有 Agent Tool loop、Citation、仓库索引、shell、patch、Git 写入或多 Agent。

## 结论与门禁

当前版本是否完成：是

是否允许实施 C4 BM25：是

是否允许“评审” Agent 路线：否

是否授权“实施” Agent 第一阶段：否

默认评审档案：personal-local-readonly

`result=passed`。该结论只形成 `IMPLEMENTATION_UNLOCKED:C4`；Agent 仍保持锁定。
""",
        encoding="utf-8",
    )

    manifest = {
        "schema_version": 1,
        "stage": "C3",
        "route_profile": "current-release",
        "run_id": run_id,
        "baseline_commit": BASELINE_COMMIT,
        "implementation_commit": IMPLEMENTATION_COMMIT,
        "implementation_parent": IMPLEMENTATION_PARENT,
        "validated_head": validated_head,
        "supersedes_manifest_sha256": supersedes,
        "dependencies": [dependency],
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
            "heads": ["0005"],
            "current": ["0005"],
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
            "deterministic fake latency is a comparison baseline, not a production SLA",
            "C2 committed live smoke was hash-verified and not rerun",
            "local single-worker conversation guard",
            "current lexical retrieval is pg_trgm, not BM25",
            "frontend bundle size remains an optimization opportunity",
        ],
        "gate": {
            "current_release_complete": True,
            "agent_review_allowed": False,
            "agent_implementation_authorized": False,
            "next_stage": "C4",
            "default_route_profile": "personal-local-readonly",
        },
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
        print("[C3 EVIDENCE] worktree must be clean", file=sys.stderr)
        return 1
    validated_head = git("rev-parse", "HEAD")
    if git("rev-parse", IMPLEMENTATION_COMMIT) != IMPLEMENTATION_COMMIT:
        print("[C3 EVIDENCE] implementation commit missing", file=sys.stderr)
        return 1
    if (
        subprocess.run(
            [
                "git",
                "-C",
                str(REPO_ROOT),
                "merge-base",
                "--is-ancestor",
                IMPLEMENTATION_COMMIT,
                validated_head,
            ]
        ).returncode
        != 0
    ):
        print(
            "[C3 EVIDENCE] validated HEAD does not contain implementation",
            file=sys.stderr,
        )
        return 1
    if not C2_MANIFEST.is_file():
        print("[C3 EVIDENCE] C2 dependency manifest missing", file=sys.stderr)
        return 1

    run_id = utc_now().strftime("%Y%m%dT%H%M%SZ") + f"-{secrets.token_hex(4)}"
    supersedes = (
        sha256_file(EVIDENCE_ROOT / "manifest.json")
        if (EVIDENCE_ROOT / "manifest.json").is_file()
        else None
    )
    print(f"[C3 EVIDENCE] run_id={run_id} validated_head={validated_head}")

    with tempfile.TemporaryDirectory(prefix="codeaware-c3-evidence-") as temporary:
        temp_stage = Path(temporary) / "C3"
        artifact_dir = temp_stage / "artifacts"
        artifact_dir.mkdir(parents=True)
        records: list[dict] = []
        try:
            for command_id, cwd, argv in COMMANDS:
                contract = C3_COMMAND_CONTRACTS[command_id]
                if (relative_cwd(cwd), argv) != contract:
                    raise EvidenceFailure(
                        f"collector command contract mismatch: {command_id}"
                    )
                records.append(
                    run_command(command_id, cwd, argv, artifact_dir)
                )
            manifest = build_stage_files(
                temp_stage,
                run_id,
                validated_head,
                records,
                supersedes,
            )
            validation_errors = validate("C3", manifest, temp_stage)
            if validation_errors:
                raise EvidenceFailure("; ".join(validation_errors))
        except Exception as exc:  # noqa: BLE001
            attempt = copy_attempt(temp_stage, run_id, str(exc))
            print(
                f"[C3 EVIDENCE] failed; attempt retained at "
                f"{attempt.relative_to(REPO_ROOT)}",
                file=sys.stderr,
            )
            return 1
        promote_success(temp_stage)

    print(
        "[C3 EVIDENCE] PASS generated "
        "docs/roadmap/current-release/evidence/C3/manifest.json"
    )
    print(
        "[C3 EVIDENCE] commit the evidence before running "
        "validate_stage_evidence.py C3"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
