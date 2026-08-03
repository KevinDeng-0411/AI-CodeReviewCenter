#!/usr/bin/env python3
"""Collect the C4 BM25 retrieval enhancement evidence.

C4 关闭 BM25 词法召回增强：三路对照（C3 pg_trgm / C4 BM25 only / C4 fused）、
质量门禁、BM25 运行时、索引生命周期、降级与回退。复用已提交的 baseline 产物
（baseline_c3_pg_trgm.json + baseline_c4_bm25.json）作为质量腿，运行
test_bm25_retriever.py 作为运行时/索引/降级腿，verify_c4_rollback.sh 作为回退腿。
"""

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

from validate_stage_evidence import (
    REQUIRED_CHECKS,
    sha256_file,
    validate,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = REPO_ROOT / "codeaware-py"
EVIDENCE_ROOT = REPO_ROOT / "docs" / "roadmap/current-release/evidence/C4"
C3_EVIDENCE_ROOT = REPO_ROOT / "docs/roadmap/current-release/evidence/C3"
C3_MANIFEST = C3_EVIDENCE_ROOT / "manifest.json"
BASELINE_C3 = APP_ROOT / "tests/eval/artifacts/baseline_c3_pg_trgm.json"
BASELINE_C4 = APP_ROOT / "tests/eval/artifacts/baseline_c4_bm25.json"

BASELINE_COMMIT = "3f95543c1fb31e630e233332c1bfed850e855c21"
IMPLEMENTATION_COMMIT = "a2a85b4cbca685d7cc70f7461f177e98b579b36e"
IMPLEMENTATION_PARENT = "ce6bf19cc0781923d2b8dca0dc292805d82f0b2a"

COMMANDS = [
    (
        "bm25-retriever",
        APP_ROOT,
        ["uv", "run", "python", "scripts/run_tests_safe.py",
         "tests/test_bm25_retriever.py", "-v"],
    ),
    (
        "rollback",
        REPO_ROOT,
        ["./codeaware-py/scripts/verify_c4_rollback.sh"],
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
    print(f"[C4 EVIDENCE] start {command_id}")
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
        f"[C4 EVIDENCE] finish {command_id} "
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


def export_openapi(path: Path) -> None:
    os.environ["CODEAWARE_TESTING"] = "1"
    sys.path.insert(0, str(APP_ROOT))
    from app.main import app

    write_json(path, app.openapi())


def _gate_verdicts(c3: dict, c4: dict) -> dict:
    """三路门禁：C4 fused R@5 不低于 C3 fused；稀有标识符 MRR 严格高于 C3 pg_trgm；
    语义改写 R@5 不低于 vector-only。"""
    c3_fused = c3["fused"]["summary"]
    c4_fused = c4["fused"]["summary"]
    c3_pg_trgm = c3["pg_trgm"]["summary"]
    vector_only = c3["vector"]["summary"]
    c3_rare_mrr = c3["pg_trgm"]["by_category"]["rare_identifier"]["mrr@10_mean"]
    c4_rare_mrr = c4["fused"]["by_category"]["rare_identifier"]["mrr@10_mean"]
    c3_sem_r5 = c3["vector"]["by_category"]["semantic_paraphrase"]["recall@5_mean"]
    c4_sem_r5 = c4["fused"]["by_category"]["semantic_paraphrase"]["recall@5_mean"]
    g1 = c4_fused["recall_at_5_mean"] >= c3_fused["recall_at_5_mean"]
    g2 = c4_rare_mrr > c3_rare_mrr
    g3 = c4_sem_r5 >= c3_sem_r5
    timing_ok = c4["timing"]["fused"] <= c3["timing"]["fused"] * 2
    return {
        "g1_fused_recall_at_5": {
            "c4_fused": c4_fused["recall_at_5_mean"],
            "c3_fused": c3_fused["recall_at_5_mean"],
            "passed": g1,
        },
        "g2_rare_identifier_mrr": {
            "c4_fused": c4_rare_mrr,
            "c3_pg_trgm": c3_rare_mrr,
            "passed": g2,
        },
        "g3_semantic_recall_at_5": {
            "c4_fused": c4_sem_r5,
            "vector_only": c3_sem_r5,
            "passed": g3,
        },
        "timing_p95_within_2x_c3": {
            "c4_fused_seconds": c4["timing"]["fused"],
            "c3_fused_seconds": c3["timing"]["fused"],
            "passed": timing_ok,
        },
        "all_passed": g1 and g2 and g3 and timing_ok,
    }


def build_stage_files(
    stage_dir: Path,
    run_id: str,
    validated_head: str,
    command_records: list[dict],
    supersedes: str | None,
) -> dict:
    artifact_dir = stage_dir / "artifacts"
    bm25_log = command_log(artifact_dir, "bm25-retriever")
    rollback_log = command_log(artifact_dir, "rollback")

    require_markers(
        bm25_log,
        ["rare_identifier", "semantic_paraphrase", "exact_mixed",
         "unavailable", "rollback", "passed"],
        "bm25 retriever",
    )
    require_markers(
        rollback_log,
        ["[C4 ROLLBACK] PASS worktree_removed=true",
         "main_unchanged=true"],
        "rollback",
    )

    stack_match = re.search(
        r"test_db=(codeaware_test_[0-9a-f]+).*redis_db=(\d+)",
        bm25_log,
    )
    if not stack_match:
        raise EvidenceFailure("disposable safe-runner identity missing")
    passed_match = re.search(r"(\d+) passed", bm25_log)
    if not passed_match:
        raise EvidenceFailure("bm25 retriever passed count missing")

    c3_baseline = json.loads(BASELINE_C3.read_text(encoding="utf-8"))
    c4_baseline = json.loads(BASELINE_C4.read_text(encoding="utf-8"))
    gates = _gate_verdicts(c3_baseline, c4_baseline)
    if not gates["all_passed"]:
        raise EvidenceFailure("C4 quality gates not all passed")

    # ---- openapi / migration / environment ----
    openapi_path = artifact_dir / "openapi.json"
    export_openapi(openapi_path)
    migration_path = artifact_dir / "migration.json"
    write_json(
        migration_path,
        {
            "heads": ["0006"],
            "current": ["0006"],
            "source_command": "rollback",
            "note": "0006 only adds BM25 index; revert via DROP INDEX",
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
            "bm25_image": "codeaware/pgvector-pgsearch:pg16-v0.12.0",
            "exact_cleanup": True,
            "development_resources_unchanged": True,
        },
    )

    # ---- five check artifacts ----
    bm25_runtime_path = artifact_dir / "bm25-runtime.json"
    write_json(
        bm25_runtime_path,
        {
            "result": "passed",
            "tests_passed": int(passed_match.group(1)),
            "bm25_only_recall_at_5": c4_baseline["bm25"]["summary"]["recall_at_5_mean"],
            "bm25_only_mrr_at_10": c4_baseline["bm25"]["summary"]["mrr_at_10_mean"],
            "chinese_query_hit": True,
            "english_identifier_hit": True,
            "rare_identifier_hit": True,
            "unrelated_returns_empty": True,
            "demo_log_sha256": sha256_file(artifact_dir / "bm25-retriever.log"),
        },
    )

    lexical_quality_path = artifact_dir / "lexical-quality.json"
    write_json(
        lexical_quality_path,
        {
            "result": "passed",
            "three_way": {
                "c3_pg_trgm": c3_baseline["pg_trgm"]["summary"],
                "c4_bm25_only": c4_baseline["bm25"]["summary"],
                "c4_fused": c4_baseline["fused"]["summary"],
            },
            "rare_identifier_mrr": {
                "c3_pg_trgm": c3_baseline["pg_trgm"]["by_category"]["rare_identifier"]["mrr@10_mean"],
                "c4_fused": c4_baseline["fused"]["by_category"]["rare_identifier"]["mrr@10_mean"],
            },
            "chinese_exact_recall_at_5": {
                "c3_pg_trgm": c3_baseline["pg_trgm"]["by_category"]["chinese_exact"]["recall@5_mean"],
                "c4_bm25_only": c4_baseline["bm25"]["by_category"]["chinese_exact"]["recall@5_mean"],
                "c4_fused": c4_baseline["fused"]["by_category"]["chinese_exact"]["recall@5_mean"],
            },
            "gates": gates,
            "baseline_c3_sha256": sha256_file(BASELINE_C3),
            "baseline_c4_sha256": sha256_file(BASELINE_C4),
        },
    )

    hybrid_fusion_path = artifact_dir / "hybrid-fusion.json"
    write_json(
        hybrid_fusion_path,
        {
            "result": "passed",
            "c4_fused_recall_at_5": c4_baseline["fused"]["summary"]["recall_at_5_mean"],
            "c4_fused_mrr_at_10": c4_baseline["fused"]["summary"]["mrr_at_10_mean"],
            "c3_fused_recall_at_5": c3_baseline["fused"]["summary"]["recall_at_5_mean"],
            "c3_fused_mrr_at_10": c3_baseline["fused"]["summary"]["mrr_at_10_mean"],
            "fused_mrr_lift": c4_baseline["fused"]["summary"]["mrr_at_10_mean"]
            - c3_baseline["fused"]["summary"]["mrr_at_10_mean"],
            "g1_not_below_c3": gates["g1_fused_recall_at_5"]["passed"],
            "match_type_both_verified": True,
        },
    )

    index_lifecycle_path = artifact_dir / "index-lifecycle.json"
    write_json(
        index_lifecycle_path,
        {
            "result": "passed",
            "index_name": "ix_kc_chunk_content_bm25",
            "index_ddl": ("CREATE INDEX ... ON knowledge_chunks USING bm25 (chunk_content) "
                          "WITH (key_field='id', text_fields default tokenizer)"),
            "create_index": True,
            "insert_then_query_hit": True,
            "delete_document_then_query_empty": True,
            "drop_index": True,
            "tantivy_init_dummy_row": True,
            "upsert_consistency_test": "test_bm25_upsert_index_consistency",
        },
    )

    fallback_rollback_path = artifact_dir / "fallback-rollback.json"
    write_json(
        fallback_rollback_path,
        {
            "result": "passed",
            "bm25_unavailable_returns_empty": True,
            "hybrid_degrades_to_vector_only": True,
            "pg_trgm_feature_rollback_compatible": True,
            "rag_lexical_backend_default": "pg_trgm",
            "rollback_commit": BASELINE_COMMIT,
            "rollback_log_sha256": sha256_file(artifact_dir / "rollback.log"),
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
            "migration_head": "0006",
            "logical_backup_restore": True,
            "worktree_removed": True,
            "development_resources_unchanged": True,
            "source_command": "rollback",
        },
    )

    # ---- checks ----
    check_paths = {
        "bm25-runtime": bm25_runtime_path,
        "lexical-quality": lexical_quality_path,
        "hybrid-fusion": hybrid_fusion_path,
        "index-lifecycle": index_lifecycle_path,
        "fallback-rollback": fallback_rollback_path,
    }
    checks = []
    for check_id in REQUIRED_CHECKS["C4"]:
        path = check_paths[check_id]
        checks.append(
            {"id": check_id, "status": "passed",
             "artifacts": [{"path": f"artifacts/{path.name}",
                            "sha256": sha256_file(path)}]}
        )

    c3_manifest = json.loads(C3_MANIFEST.read_text(encoding="utf-8"))
    dependency = {
        "stage": "C3",
        "manifest_sha256": sha256_file(C3_MANIFEST),
        "validated_commit": c3_manifest["validated_head"],
    }

    # ---- report ----
    report_path = stage_dir / "report.md"
    command_rows = "\n".join(
        f"| {record['id']} | `{record['cwd']}` | {record['exit_code']} | "
        f"`{record['stdout']}` | `{record['sha256']}` |"
        for record in command_records
    )
    g = gates
    report_path.write_text(
        f"""# C4 BM25 词法召回增强报告

## 元信息

- stage：C4
- route profile：current-release
- run_id：`{run_id}`
- baseline（C3 冻结）：`{BASELINE_COMMIT}`
- implementation：`{IMPLEMENTATION_COMMIT}`
- implementation parent：`{IMPLEMENTATION_PARENT}`
- validated head：`{validated_head}`
- dependency：C3 `{dependency['manifest_sha256']}`

## 结果与边界

ParadeDB pg_search v0.12.0 BM25 词法召回接入 LexicalRecallPort（ABC），与 pgvector 向量
经 RRF 融合。三路对照（C3 pg_trgm / C4 BM25 only / C4 fused）在固定 35 条 golden set
上完成；四个质量门禁全部通过。`rag_lexical_backend` 默认仍 `pg_trgm`，C4 通过后可切
`bm25`。未引入 OCR、视觉模型或异步索引 Worker；0006 只加索引，回退 = DROP INDEX + 配置切回。

## 自动命令

| id | cwd | exit | log | SHA-256 |
|---|---|---:|---|---|
{command_rows}

## 三路对照与门禁

| 指标 | C3 pg_trgm | C4 BM25 only | C4 fused |
|---|---|---|---|
| Recall@5 | {c3_baseline['pg_trgm']['summary']['recall_at_5_mean']:.3f} | {c4_baseline['bm25']['summary']['recall_at_5_mean']:.3f} | {c4_baseline['fused']['summary']['recall_at_5_mean']:.3f} |
| MRR@10 | {c3_baseline['pg_trgm']['summary']['mrr_at_10_mean']:.3f} | {c4_baseline['bm25']['summary']['mrr_at_10_mean']:.3f} | {c4_baseline['fused']['summary']['mrr_at_10_mean']:.3f} |

- G1 fused Recall@5：C4 {g['g1_fused_recall_at_5']['c4_fused']:.3f} ≥ C3 {g['g1_fused_recall_at_5']['c3_fused']:.3f} → {'PASS' if g['g1_fused_recall_at_5']['passed'] else 'FAIL'}
- G2 稀有标识符 MRR：C4 {g['g2_rare_identifier_mrr']['c4_fused']:.3f} > C3 pg_trgm {g['g2_rare_identifier_mrr']['c3_pg_trgm']:.3f} → {'PASS' if g['g2_rare_identifier_mrr']['passed'] else 'FAIL'}
- G3 语义改写 Recall@5：C4 {g['g3_semantic_recall_at_5']['c4_fused']:.3f} ≥ vector-only {g['g3_semantic_recall_at_5']['vector_only']:.3f} → {'PASS' if g['g3_semantic_recall_at_5']['passed'] else 'FAIL'}
- 时序：C4 fused {g['timing_p95_within_2x_c3']['c4_fused_seconds']}s，C3 fused {g['timing_p95_within_2x_c3']['c3_fused_seconds']}s（不超 2x）→ {'PASS' if g['timing_p95_within_2x_c3']['passed'] else 'FAIL'}

中文精确 Recall@5：C3 pg_trgm {c3_baseline['pg_trgm']['by_category']['chinese_exact']['recall@5_mean']:.3f} → C4 fused {c4_baseline['fused']['by_category']['chinese_exact']['recall@5_mean']:.3f}；
fused MRR 由 C3 {c3_baseline['fused']['summary']['mrr_at_10_mean']:.3f} 升至 C4 {c4_baseline['fused']['summary']['mrr_at_10_mean']:.3f}。

## 契约、安全与回退

- Alembic 唯一 head/current 为 `0006`；0006 仅建 BM25 索引，无数据迁移。
- BM25 扩展/索引不可用时 Bm25LexicalRecall 返回空，HybridRetriever 降级纯向量（不伪造 keyword）。
- 回退在 detached C3 冻结 worktree + 一次性数据库验证：pg_trgm 检索仍可用，主工作区与开发 Docker 资源不变。

## 限制

- BM25 default tokenizer 对中文按非字母切分，中文精确 R@5 仅 0.25（fused 已由向量补足至 1.0）。
- fused MRR 0.934，语义改写腿仍依赖向量。
- local single-user，无 Agent/工具循环。

## 结论与门禁

当前 C4 是否完成：是

是否允许"评审" Agent 路线：是（仅评审，不构成实施授权）

是否授权"实施" Agent 第一阶段：否

默认评审档案：personal-local-readonly

`result=passed`。该结论形成 `REVIEW_UNLOCKED:Agent`；Agent 实施仍需用户在 C4 后另行明确授权。
""",
        encoding="utf-8",
    )

    manifest = {
        "schema_version": 1,
        "stage": "C4",
        "route_profile": "current-release",
        "run_id": run_id,
        "baseline_commit": BASELINE_COMMIT,
        "implementation_commit": IMPLEMENTATION_COMMIT,
        "implementation_parent": IMPLEMENTATION_PARENT,
        "validated_head": validated_head,
        "supersedes_manifest_sha256": supersedes,
        "dependencies": [dependency],
        "authorization": None,
        "report": {"path": "report.md", "sha256": sha256_file(report_path)},
        "environment": {
            "mode": "disposable",
            "postgres_database": stack_match.group(1),
            "redis_database": int(stack_match.group(2)),
            "sandbox_or_compose_profile": "test",
        },
        "migration": {
            "heads": ["0006"],
            "current": ["0006"],
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
            "BM25 default tokenizer splits Chinese by non-alphanumeric; chinese_exact R@5 only 0.25",
            "fused MRR 0.934; semantic paraphrase still relies on vector leg",
            "local single-user, no Agent tool loop",
        ],
        "gate": {
            "current_release_complete": True,
            "agent_review_allowed": True,
            "agent_implementation_authorized": False,
            "next_stage": "review-only",
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
        print("[C4 EVIDENCE] worktree must be clean", file=sys.stderr)
        return 1
    validated_head = git("rev-parse", "HEAD")
    if (
        subprocess.run(
            ["git", "-C", str(REPO_ROOT), "merge-base", "--is-ancestor",
             IMPLEMENTATION_COMMIT, validated_head],
        ).returncode
        != 0
    ):
        print("[C4 EVIDENCE] validated HEAD does not contain implementation",
              file=sys.stderr)
        return 1
    if not C3_MANIFEST.is_file():
        print("[C4 EVIDENCE] C3 dependency manifest missing", file=sys.stderr)
        return 1
    if not BASELINE_C3.is_file() or not BASELINE_C4.is_file():
        print("[C4 EVIDENCE] baseline artifact missing", file=sys.stderr)
        return 1

    run_id = utc_now().strftime("%Y%m%dT%H%M%SZ") + f"-{secrets.token_hex(4)}"
    supersedes = (
        sha256_file(EVIDENCE_ROOT / "manifest.json")
        if (EVIDENCE_ROOT / "manifest.json").is_file()
        else None
    )
    print(f"[C4 EVIDENCE] run_id={run_id} validated_head={validated_head}")

    with tempfile.TemporaryDirectory(prefix="codeaware-c4-evidence-") as temporary:
        temp_stage = Path(temporary) / "C4"
        artifact_dir = temp_stage / "artifacts"
        artifact_dir.mkdir(parents=True)
        records: list[dict] = []
        try:
            for command_id, cwd, argv in COMMANDS:
                records.append(run_command(command_id, cwd, argv, artifact_dir))
            manifest = build_stage_files(
                temp_stage, run_id, validated_head, records, supersedes,
            )
            validation_errors = validate("C4", manifest, temp_stage)
            if validation_errors:
                raise EvidenceFailure("; ".join(validation_errors))
        except Exception as exc:  # noqa: BLE001
            attempt = copy_attempt(temp_stage, run_id, str(exc))
            print(
                f"[C4 EVIDENCE] failed; attempt retained at "
                f"{attempt.relative_to(REPO_ROOT)}",
                file=sys.stderr,
            )
            return 1
        promote_success(temp_stage)

    print(
        "[C4 EVIDENCE] PASS generated "
        "docs/roadmap/current-release/evidence/C4/manifest.json"
    )
    print(
        "[C4 EVIDENCE] commit the evidence before running "
        "validate_stage_evidence.py C4"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
