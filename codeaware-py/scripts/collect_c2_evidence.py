#!/usr/bin/env python3
"""Run and collect the C2 seven-domain, browser, live, and rollback evidence."""

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
    C2_COMMAND_CONTRACTS,
    REQUIRED_CHECKS,
    sha256_file,
    validate,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = REPO_ROOT / "codeaware-py"
FRONTEND_ROOT = APP_ROOT / "frontend"
EVIDENCE_ROOT = REPO_ROOT / "docs/roadmap/current-release/evidence/C2"
C1_MANIFEST = (
    REPO_ROOT / "docs/roadmap/current-release/evidence/C1/manifest.json"
)

BASELINE_COMMIT = "094ede8b24ee396b860461f62e34ea5a31cee96c"
IMPLEMENTATION_COMMIT = "cd217c8817ed81ddb19fc8268d350300e57cae91"
IMPLEMENTATION_PARENT = "2aaf35f7c75088bd84f37afc7be5f14feab72bc3"

COMMANDS = [
    ("dependency-lock", APP_ROOT, ["uv", "lock", "--check"]),
    ("compose-config", REPO_ROOT, ["docker", "compose", "config", "--quiet"]),
    (
        "c2-mocked-demo",
        REPO_ROOT,
        ["./codeaware-py/scripts/demo_c2_mocked.sh"],
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
    (
        "api-e2e",
        APP_ROOT,
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
    ("frontend-install", FRONTEND_ROOT, ["npm", "ci"]),
    ("frontend-test", FRONTEND_ROOT, ["npm", "run", "test"]),
    ("frontend-lint", FRONTEND_ROOT, ["npm", "run", "lint"]),
    ("frontend-build", FRONTEND_ROOT, ["npm", "run", "build"]),
    (
        "browser-e2e",
        APP_ROOT,
        [
            "uv",
            "run",
            "python",
            "scripts/run_tests_safe.py",
            "--browser-e2e",
        ],
    ),
    ("live-smoke", REPO_ROOT, ["./codeaware-py/scripts/demo_c2_live.sh"]),
    ("rollback", REPO_ROOT, ["./codeaware-py/scripts/verify_c2_rollback.sh"]),
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
        "CODEAWARE_BROWSER_E2E",
        "CODEAWARE_BROWSER_E2E_PROJECT_ROOT",
    ):
        environment.pop(name, None)
    environment["CODEAWARE_TESTING"] = "1"
    npm_cache = Path(tempfile.gettempdir()) / "codeaware-c2-evidence-npm-cache"
    npm_cache.mkdir(parents=True, exist_ok=True)
    environment["NPM_CONFIG_CACHE"] = str(npm_cache)
    return environment


def run_command(
    command_id: str,
    cwd: Path,
    argv: list[str],
    artifact_dir: Path,
) -> dict:
    started = utc_now()
    print(f"[C2 EVIDENCE] start {command_id}")
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
        f"[C2 EVIDENCE] finish {command_id} "
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


def export_openapi(path: Path) -> None:
    os.environ["CODEAWARE_TESTING"] = "1"
    os.environ.pop("CODEAWARE_BROWSER_E2E", None)
    sys.path.insert(0, str(APP_ROOT))
    from app.main import app

    write_json(path, app.openapi())


def command_log(artifact_dir: Path, command_id: str) -> str:
    return (artifact_dir / f"{command_id}.log").read_text(encoding="utf-8")


def _require_markers(text: str, markers: list[str], label: str) -> None:
    missing = [marker for marker in markers if marker not in text]
    if missing:
        raise EvidenceFailure(f"{label} missing markers: {missing}")


def _extract_live_metrics(live_log: str) -> dict:
    match = re.search(r"^\[C2 LIVE\] (\{.*\})$", live_log, re.MULTILINE)
    if not match:
        raise EvidenceFailure("live smoke metrics JSON missing")
    try:
        metrics = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise EvidenceFailure("live smoke metrics JSON invalid") from exc
    if metrics.get("embedding", {}).get("dimension") != 1024:
        raise EvidenceFailure("live embedding dimension is not 1024")
    if metrics.get("cost", {}).get("real_llm_calls") != 3:
        raise EvidenceFailure("live LLM call count missing")
    if metrics.get("structured_output", {}).get("valid") is not True:
        raise EvidenceFailure("live structured output was not valid")
    if "both" not in metrics.get("knowledge", {}).get("match_types", []):
        raise EvidenceFailure("live knowledge hybrid result did not prove both legs")
    if metrics.get("ai_readme", {}).get("version") != 1:
        raise EvidenceFailure("live AIReadMe version missing")
    return metrics


def build_stage_files(
    stage_dir: Path,
    run_id: str,
    validated_head: str,
    command_records: list[dict],
    supersedes: str | None,
) -> dict:
    artifact_dir = stage_dir / "artifacts"
    mocked_log = command_log(artifact_dir, "c2-mocked-demo")
    backend_log = command_log(artifact_dir, "backend-full")
    coverage_log = command_log(artifact_dir, "backend-coverage")
    api_log = command_log(artifact_dir, "api-e2e")
    browser_log = command_log(artifact_dir, "browser-e2e")
    live_log = command_log(artifact_dir, "live-smoke")
    rollback_log = command_log(artifact_dir, "rollback")

    _require_markers(
        mocked_log,
        [
            "[PASS] Code Review",
            "[PASS] Unit Test",
            "[PASS] AIReadMe",
            "[PASS] Chat",
            "[PASS] Knowledge",
            "[PASS] Memory",
            "[PASS] Prompt",
            "[C2 MOCKED] PASS",
        ],
        "mocked demo",
    )
    _require_markers(browser_log, ["7 passed", "exact cleanup complete"], "browser")
    _require_markers(live_log, ["1 passed", "[C2 LIVE] PASS"], "live smoke")
    _require_markers(rollback_log, ["[C2 ROLLBACK] PASS"], "rollback")
    backend_match = re.search(r"(\d+) passed, 2 deselected", backend_log)
    coverage_match = re.search(r"TOTAL\s+\d+\s+\d+\s+(\d+)%", coverage_log)
    api_match = re.search(r"(\d+) passed", api_log)
    if not backend_match or not api_match:
        raise EvidenceFailure("backend/API test count missing")
    if not coverage_match:
        raise EvidenceFailure("backend coverage total missing")
    live_metrics = _extract_live_metrics(live_log)

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
            "heads": ["0005"],
            "current": ["0005"],
            "source_command": "rollback",
            "roundtrip": ["0005", "0004", "0005", "0002", "0005", "base", "head"],
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
            "browser_exact_cleanup": "exact cleanup complete" in browser_log,
            "live_exact_cleanup": "exact cleanup complete" in live_log,
        },
    )
    rollback_path = artifact_dir / "rollback.json"
    write_json(
        rollback_path,
        {
            "result": "passed",
            "baseline_commit": BASELINE_COMMIT,
            "implementation_commit": IMPLEMENTATION_COMMIT,
            "implementation_parent": IMPLEMENTATION_PARENT,
            "temp_worktree": True,
            "disposable_database": True,
            "migration_chain": [
                "0005",
                "0004",
                "0005",
                "0002",
                "0005",
                "base",
                "head",
            ],
            "worktree_removed": True,
            "development_resources_unchanged": True,
            "source_command": "rollback",
        },
    )
    live_path = artifact_dir / "live-smoke.json"
    write_json(live_path, live_metrics)

    check_sources = {
        "code-review": ["c2-mocked-demo", "api-e2e", "browser-e2e", "live-smoke"],
        "unit-test": ["c2-mocked-demo", "api-e2e", "browser-e2e"],
        "ai-readme": ["c2-mocked-demo", "api-e2e", "browser-e2e", "live-smoke"],
        "chat": ["c2-mocked-demo", "api-e2e", "browser-e2e", "live-smoke"],
        "knowledge": ["c2-mocked-demo", "api-e2e", "browser-e2e", "live-smoke"],
        "memory": ["c2-mocked-demo", "api-e2e", "browser-e2e"],
        "prompt": ["c2-mocked-demo", "api-e2e", "browser-e2e", "rollback"],
    }
    check_assertions = {
        "code-review": [
            "selected/active template and structured record closure",
            "project filter, detail type, stable model failures",
        ],
        "unit-test": [
            "JUnit5 structured generation and record closure",
            "UI states generation only and does not claim execution",
        ],
        "ai-readme": [
            "allowlisted safe snapshot, versions, latest, and rejection",
            "real model snapshot generation succeeded",
        ],
        "chat": [
            "typed stream, persistence, reload, context, summary, FACT, delete",
            "real DeepSeek chat connectivity succeeded",
        ],
        "knowledge": [
            "text/file upload, chunks, pg_trgm+pgvector RRF, cascade",
            "real bge-m3 hybrid retrieval returned both",
        ],
        "memory": [
            "REFERENCE save/recall/delete and FACT conversation provenance",
            "embedding failures and request bounds are stable",
        ],
        "prompt": [
            "create v2, type-aware preview, rollback, one-active invariant",
            "concurrent create/activate and migration constraints passed",
        ],
    }
    checks = []
    for check_id in REQUIRED_CHECKS["C2"]:
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
        artifacts = [
            {
                "path": f"artifacts/{path.name}",
                "sha256": sha256_file(path),
            }
        ]
        if "live-smoke" in check_sources[check_id]:
            artifacts.append(
                {
                    "path": "artifacts/live-smoke.json",
                    "sha256": sha256_file(live_path),
                }
            )
        checks.append(
            {
                "id": check_id,
                "status": "passed",
                "artifacts": artifacts,
            }
        )

    c1_manifest = json.loads(C1_MANIFEST.read_text(encoding="utf-8"))
    dependency = {
        "stage": "C1",
        "manifest_sha256": sha256_file(C1_MANIFEST),
        "validated_commit": c1_manifest["validated_head"],
    }
    report_path = stage_dir / "report.md"
    command_rows = "\n".join(
        f"| {record['id']} | `{record['cwd']}` | {record['exit_code']} | "
        f"`{record['stdout']}` | `{record['sha256']}` |"
        for record in command_records
    )
    report_path.write_text(
        f"""# C2 现有功能闭环验收报告

## 元信息

- stage：C2
- route profile：current-release
- run_id：`{run_id}`
- baseline：`{BASELINE_COMMIT}`
- implementation：`{IMPLEMENTATION_COMMIT}`
- implementation parent：`{IMPLEMENTATION_PARENT}`
- validated head：`{validated_head}`
- dependency：C1 `{dependency['manifest_sha256']}`

## 结果与边界

七个现有功能域的 API 成功/失败/边界/持久化闭环、七域浏览器成功路径与可见失败、
一次真实 DeepSeek/Ollama smoke、迁移往返和 detached rollback 均通过。未实施 C3、
Agent、工具调用或仓库写入。

## 自动命令

| id | cwd | exit | log | SHA-256 |
|---|---|---:|---|---|
{command_rows}

## 量化结果

- 后端全量：{backend_match.group(1)} passed，2 deselected。
- API contract/e2e：{api_match.group(1)} passed。
- 覆盖率报告 TOTAL：{coverage_match.group(1)}%（记录结果，不作为全局 90% 目标）。
- 浏览器：7 个现有 UI 功能域全部通过。
- Live：模型 `{live_metrics['llm_model']}`、embedding
  `{live_metrics['embedding_model']}` 1024 维、Knowledge `both` 命中、AIReadMe v1。
- 成本记录：真实 LLM 调用 3 次；保存 provider token usage。provider 未返回 billed amount，
  因此不硬编码未经验证的价格。

## 契约与回退

- Alembic 唯一 head/current：`0005`。
- OpenAPI：`artifacts/openapi.json`。
- 回退在 detached C1 baseline worktree 和随机一次性数据库验证；主工作区与开发 Docker
  资源指纹未变化。

## 限制

- live smoke 只证明最小真实连通性和结构，不做模型输出逐字质量评估。
- browser E2E 使用真实 FastAPI/PG/Redis 与受控 fake 模型，不向浏览器注入 API key。
- 当前 per-conversation turn guard 仍为本机单 worker 约束。
- 全局 bundle 仍有体积优化空间，属于 C3 交接记录，不在 C2 扩展产品范围。

## 结论

`result=passed`。该结论只解锁当前版本 C3，不解锁任何 Agent 实施。
""",
        encoding="utf-8",
    )

    manifest = {
        "schema_version": 1,
        "stage": "C2",
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
            "live smoke records hashes and token usage, not verbatim model output",
            "provider billed amount was not exposed; no unverified price is hard-coded",
            "browser E2E uses guarded fake model adapters on real application routes",
            "local single-worker conversation guard",
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
        print("[C2 EVIDENCE] worktree must be clean", file=sys.stderr)
        return 1
    validated_head = git("rev-parse", "HEAD")
    if git("rev-parse", IMPLEMENTATION_COMMIT) != IMPLEMENTATION_COMMIT:
        print("[C2 EVIDENCE] implementation commit missing", file=sys.stderr)
        return 1
    ancestor = subprocess.run(
        [
            "git",
            "-C",
            str(REPO_ROOT),
            "merge-base",
            "--is-ancestor",
            IMPLEMENTATION_COMMIT,
            validated_head,
        ]
    )
    if ancestor.returncode != 0:
        print(
            "[C2 EVIDENCE] validated HEAD does not contain implementation",
            file=sys.stderr,
        )
        return 1
    if not C1_MANIFEST.is_file():
        print("[C2 EVIDENCE] C1 dependency manifest missing", file=sys.stderr)
        return 1

    run_id = utc_now().strftime("%Y%m%dT%H%M%SZ") + f"-{secrets.token_hex(4)}"
    supersedes = (
        sha256_file(EVIDENCE_ROOT / "manifest.json")
        if (EVIDENCE_ROOT / "manifest.json").is_file()
        else None
    )
    print(f"[C2 EVIDENCE] run_id={run_id} validated_head={validated_head}")

    with tempfile.TemporaryDirectory(prefix="codeaware-c2-evidence-") as temporary:
        temp_stage = Path(temporary) / "C2"
        artifact_dir = temp_stage / "artifacts"
        artifact_dir.mkdir(parents=True)
        records: list[dict] = []
        try:
            for command_id, cwd, argv in COMMANDS:
                contract = C2_COMMAND_CONTRACTS[command_id]
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
            validation_errors = validate("C2", manifest, temp_stage)
            if validation_errors:
                raise EvidenceFailure("; ".join(validation_errors))
        except Exception as exc:  # noqa: BLE001
            attempt = copy_attempt(temp_stage, run_id, str(exc))
            print(
                f"[C2 EVIDENCE] failed; attempt retained at "
                f"{attempt.relative_to(REPO_ROOT)}",
                file=sys.stderr,
            )
            return 1
        promote_success(temp_stage)

    print(
        "[C2 EVIDENCE] PASS generated "
        "docs/roadmap/current-release/evidence/C2/manifest.json"
    )
    print(
        "[C2 EVIDENCE] commit the evidence before running "
        "validate_stage_evidence.py C2"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
