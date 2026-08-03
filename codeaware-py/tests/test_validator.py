"""C1-D evidence validator route, dependency, and artifact tests."""

import hashlib
import json
import subprocess

from validate_stage_evidence import (
    C1_REQUIRED_COMMANDS,
    C2_COMMAND_CONTRACTS,
    C2_REQUIRED_COMMANDS,
    C3_COMMAND_CONTRACTS,
    C3_REQUIRED_COMMANDS,
    DAG,
    manifest_path_for,
    REQUIRED_CHECKS,
    sha256_file,
    validate,
    validate_evidence_commit,
)

REPO_ROOT = __import__("pathlib").Path(__file__).resolve().parents[2]


def _git(args: list[str]) -> str:
    return subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args],
        capture_output=True,
        text=True,
    ).stdout.strip()


def _hash(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _base_c1_manifest(tmp_path) -> dict:
    head = _git(["rev-parse", "HEAD"])
    report = tmp_path / "report.md"
    command_log = tmp_path / "backend.log"
    check_artifact = tmp_path / "check.log"
    migration_artifact = tmp_path / "migration.json"
    openapi_artifact = tmp_path / "openapi.json"
    rollback_artifact = tmp_path / "rollback.json"
    report.write_text("# C1 report\n", encoding="utf-8")
    command_log.write_text("passed\n", encoding="utf-8")
    check_artifact.write_text("passed\n", encoding="utf-8")
    migration_artifact.write_text(
        json.dumps({"heads": ["0004"], "current": ["0004"]}),
        encoding="utf-8",
    )
    openapi_artifact.write_text(json.dumps({"openapi": "3.1.0"}), encoding="utf-8")
    rollback_artifact.write_text(
        json.dumps({"result": "passed"}),
        encoding="utf-8",
    )
    return {
        "schema_version": 1,
        "stage": "C1",
        "route_profile": "current-release",
        "run_id": "20260730T000000Z-a1b2c3d4",
        "baseline_commit": _git(["rev-parse", "HEAD~3"]),
        "implementation_commit": head,
        "implementation_parent": _git(["rev-parse", "HEAD^"]),
        "validated_head": head,
        "supersedes_manifest_sha256": None,
        "dependencies": [],
        "authorization": None,
        "report": {"path": "report.md", "sha256": _hash(report)},
        "environment": {
            "mode": "disposable",
            "postgres_database": "codeaware_test_a1b2c3d4",
            "redis_database": 1,
            "sandbox_or_compose_profile": "test",
        },
        "migration": {
            "heads": ["0004"],
            "current": ["0004"],
            "log": "migration.json",
            "sha256": _hash(migration_artifact),
        },
        "openapi": {
            "path": "openapi.json",
            "sha256": _hash(openapi_artifact),
        },
        "commands": [
            {
                "id": command_id,
                "argv": ["python", "scripts/run_tests_safe.py", "-q"],
                "cwd": "codeaware-py",
                "exit_code": 0,
                "started_at": "2026-07-30T00:00:00Z",
                "finished_at": "2026-07-30T00:01:00Z",
                "stdout": "backend.log",
                "sha256": _hash(command_log),
                "required": True,
            }
            for command_id in sorted(C1_REQUIRED_COMMANDS)
        ],
        "checks": [
            {
                "id": check_id,
                "status": "passed",
                "artifacts": [{"path": "check.log", "sha256": _hash(check_artifact)}],
            }
            for check_id in REQUIRED_CHECKS["C1"]
        ],
        "rollback": {
            "temp_worktree": True,
            "disposable_database": True,
            "result": "passed",
            "artifact": "rollback.json",
            "sha256": _hash(rollback_artifact),
        },
        "limitations": [],
        "result": "passed",
    }


def _base_c2_manifest(tmp_path) -> dict:
    manifest = _base_c1_manifest(tmp_path)
    c1_path = manifest_path_for("C1")
    c1_manifest = json.loads(c1_path.read_text(encoding="utf-8"))
    migration = tmp_path / "migration.json"
    migration.write_text(
        json.dumps({"heads": ["0005"], "current": ["0005"]}),
        encoding="utf-8",
    )
    command_log = tmp_path / "backend.log"
    command_log.write_text(
        "\n".join(
            [
                "[PASS] Code Review",
                "[PASS] Unit Test",
                "[PASS] AIReadMe",
                "[PASS] Chat",
                "[PASS] Knowledge",
                "[PASS] Memory",
                "[PASS] Prompt",
                "[C2 MOCKED] PASS",
                "249 passed, 2 deselected",
                "7 passed",
                '"dimension": 1024',
                '"real_llm_calls": 3',
                "[C2 LIVE] PASS",
                "[C2 ROLLBACK] PASS",
                "exact cleanup complete",
            ]
        ),
        encoding="utf-8",
    )
    manifest.update(
        {
            "stage": "C2",
            "migration": {
                "heads": ["0005"],
                "current": ["0005"],
                "log": "migration.json",
                "sha256": _hash(migration),
            },
            "dependencies": [
                {
                    "stage": "C1",
                    "manifest_sha256": sha256_file(c1_path),
                    "validated_commit": c1_manifest["validated_head"],
                }
            ],
            "commands": [
                {
                    "id": command_id,
                    "argv": argv,
                    "cwd": cwd,
                    "exit_code": 0,
                    "started_at": "2026-07-30T00:00:00Z",
                    "finished_at": "2026-07-30T00:01:00Z",
                    "stdout": "backend.log",
                    "sha256": _hash(command_log),
                    "required": True,
                }
                for command_id, (cwd, argv) in sorted(
                    C2_COMMAND_CONTRACTS.items()
                )
            ],
            "checks": [
                {
                    "id": check_id,
                    "status": "passed",
                    "artifacts": [
                        {
                            "path": "check.log",
                            "sha256": _hash(tmp_path / "check.log"),
                        }
                    ],
                }
                for check_id in REQUIRED_CHECKS["C2"]
            ],
        }
    )
    assert set(C2_REQUIRED_COMMANDS) == set(C2_COMMAND_CONTRACTS)
    return manifest


def _base_c3_manifest(tmp_path) -> dict:
    manifest = _base_c2_manifest(tmp_path)
    c2_path = manifest_path_for("C2")
    c2_manifest = json.loads(c2_path.read_text(encoding="utf-8"))
    command_log = tmp_path / "backend.log"
    command_log.write_text(
        "\n".join(
            [
                "[C3 VERIFY] PASS fresh-bootstrap exit=0",
                "[C3 VERIFY] PASS backend-full exit=0",
                "[C3 VERIFY] PASS backend-coverage exit=0",
                "[C3 VERIFY] PASS release-metrics exit=0",
                "[C3 VERIFY] PASS browser-e2e exit=0",
                "[C3 VERIFY] PASS release=0.1.0",
                "repository_status_unchanged=true",
                "development_resources_unchanged=true",
                "[C3 METRICS]",
                "[PASS] Code Review",
                "[PASS] Prompt",
                "[C3 HANDOFF] PASS C2 committed live-smoke evidence hash revalidated",
                "[C3 HANDOFF] PASS repository_status_unchanged=true",
                "[C3 BACKUP] PASS",
                "[C3 ROLLBACK] PASS worktree_removed=true backup_restore=true main_unchanged=true",
            ]
        ),
        encoding="utf-8",
    )
    manifest.update(
        {
            "stage": "C3",
            "dependencies": [
                {
                    "stage": "C2",
                    "manifest_sha256": sha256_file(c2_path),
                    "validated_commit": c2_manifest["validated_head"],
                }
            ],
            "commands": [
                {
                    "id": command_id,
                    "argv": argv,
                    "cwd": cwd,
                    "exit_code": 0,
                    "started_at": "2026-07-30T00:00:00Z",
                    "finished_at": "2026-07-30T00:01:00Z",
                    "stdout": "backend.log",
                    "sha256": _hash(command_log),
                    "required": True,
                }
                for command_id, (cwd, argv) in sorted(
                    C3_COMMAND_CONTRACTS.items()
                )
            ],
            "checks": [
                {
                    "id": check_id,
                    "status": "passed",
                    "artifacts": [
                        {
                            "path": "check.log",
                            "sha256": _hash(tmp_path / "check.log"),
                        }
                    ],
                }
                for check_id in REQUIRED_CHECKS["C3"]
            ],
            "gate": {
                "current_release_complete": True,
                "agent_review_allowed": False,
                "agent_implementation_authorized": False,
                "next_stage": "C4",
                "default_route_profile": "personal-local-readonly",
            },
        }
    )
    assert set(C3_REQUIRED_COMMANDS) == set(C3_COMMAND_CONTRACTS)
    return manifest


def test_accepts_well_formed_c1(tmp_path):
    assert validate("C1", _base_c1_manifest(tmp_path), tmp_path) == []


def test_accepts_well_formed_c2_with_live_and_browser_logs(tmp_path):
    assert validate("C2", _base_c2_manifest(tmp_path), tmp_path) == []


def test_accepts_well_formed_c3_with_locked_agent_gate(tmp_path):
    assert validate("C3", _base_c3_manifest(tmp_path), tmp_path) == []


def test_rejects_c3_wrong_command_or_agent_gate(tmp_path):
    manifest = _base_c3_manifest(tmp_path)
    manifest["commands"][0]["argv"] = ["pytest"]
    manifest["gate"]["agent_implementation_authorized"] = True
    errors = validate("C3", manifest, tmp_path)
    assert any("argv 与冻结契约不一致" in error for error in errors)
    assert any("只解锁 C4" in error for error in errors)


def test_rejects_c2_missing_live_marker_or_wrong_browser_command(tmp_path):
    manifest = _base_c2_manifest(tmp_path)
    log = tmp_path / "backend.log"
    log.write_text(log.read_text(encoding="utf-8").replace("[C2 LIVE] PASS", "failed"))
    digest = _hash(log)
    for command in manifest["commands"]:
        command["sha256"] = digest
        if command["id"] == "browser-e2e":
            command["argv"] = ["npm", "run", "test:e2e"]
    errors = validate("C2", manifest, tmp_path)
    assert any("live-smoke 日志缺少标记" in error for error in errors)
    assert any("browser-e2e argv" in error for error in errors)


def test_rejects_wrong_route_profile(tmp_path):
    manifest = _base_c1_manifest(tmp_path)
    manifest["route_profile"] = "personal-local-readonly"
    assert any("route_profile" in error for error in validate("C1", manifest, tmp_path))


def test_rejects_missing_required_check(tmp_path):
    manifest = _base_c1_manifest(tmp_path)
    manifest["checks"] = [
        check for check in manifest["checks"] if check["id"] != "C1-A"
    ]
    assert any("C1-A" in error for error in validate("C1", manifest, tmp_path))


def test_rejects_extra_check_or_missing_required_command(tmp_path):
    manifest = _base_c1_manifest(tmp_path)
    manifest["checks"].append(
        {
            "id": "pretend-pass",
            "status": "passed",
            "artifacts": manifest["checks"][0]["artifacts"],
        }
    )
    manifest["commands"] = manifest["commands"][1:]
    errors = validate("C1", manifest, tmp_path)
    assert any("checks 必须精确" in error for error in errors)
    assert any("C1 commands 必须精确" in error for error in errors)


def test_rejects_migration_mismatch_and_bad_rollback_hash(tmp_path):
    manifest = _base_c1_manifest(tmp_path)
    manifest["migration"]["current"] = ["0003"]
    manifest["rollback"]["sha256"] = "0" * 64
    errors = validate("C1", manifest, tmp_path)
    assert any("heads/current" in error for error in errors)
    assert any("rollback.artifact sha256 不符" in error for error in errors)


def test_rejects_absolute_path_or_secret_in_artifact(tmp_path):
    manifest = _base_c1_manifest(tmp_path)
    artifact = tmp_path / "check.log"
    artifact.write_text(
        "workspace=/Users/example/private/repo\nLLM_API_KEY=secret\n",
        encoding="utf-8",
    )
    digest = _hash(artifact)
    for check in manifest["checks"]:
        check["artifacts"] = [{"path": "check.log", "sha256": digest}]
    errors = validate("C1", manifest, tmp_path)
    assert any("宿主路径、凭据" in error for error in errors)


def test_rejects_invalid_command_time_order(tmp_path):
    manifest = _base_c1_manifest(tmp_path)
    manifest["commands"][0]["finished_at"] = "2026-07-29T23:59:00Z"
    assert any("时间格式或顺序" in error for error in validate("C1", manifest, tmp_path))


def test_rejects_wrong_dependencies(tmp_path):
    manifest = _base_c1_manifest(tmp_path)
    manifest["stage"] = "C2"
    manifest["dependencies"] = [{"stage": "S1"}]
    assert any("依赖不符" in error for error in validate("C2", manifest, tmp_path))


def test_rejects_result_not_passed(tmp_path):
    manifest = _base_c1_manifest(tmp_path)
    manifest["result"] = "failed"
    assert any("result" in error for error in validate("C1", manifest, tmp_path))


def test_rejects_bad_git_ancestry(tmp_path):
    manifest = _base_c1_manifest(tmp_path)
    manifest["implementation_parent"] = _git(["rev-parse", "HEAD~2"])
    assert any(
        "implementation_parent" in error for error in validate("C1", manifest, tmp_path)
    )


def test_rejects_escaping_or_bad_hash_artifact(tmp_path):
    manifest = _base_c1_manifest(tmp_path)
    manifest["checks"][0]["artifacts"][0] = {
        "path": "../outside.log",
        "sha256": "bad",
    }
    assert any("路径逃逸" in error for error in validate("C1", manifest, tmp_path))


def test_rejects_required_command_without_hashed_log(tmp_path):
    manifest = _base_c1_manifest(tmp_path)
    manifest["commands"][0]["stdout"] = "missing.log"
    assert any("不存在" in error for error in validate("C1", manifest, tmp_path))


def test_unknown_stage_is_rejected_directly(tmp_path):
    assert validate("S3", {}, tmp_path) == ["未知 stage: S3"]


def test_personal_route_skips_s3_and_keeps_required_regressions():
    assert DAG["C4"] == ["C3"]
    assert DAG["S1"] == ["C4"]
    assert DAG["S4"] == ["S2"]
    assert "S3" not in DAG
    assert REQUIRED_CHECKS["C4"] == [
        "bm25-runtime",
        "lexical-quality",
        "hybrid-fusion",
        "index-lifecycle",
        "fallback-rollback",
    ]
    assert "chat-runtime-regression" in REQUIRED_CHECKS["S4"]
    assert {"source-unchanged", "profile-safety-locks"} <= set(REQUIRED_CHECKS["S5"])


def test_fake_s3_dependency_is_not_accepted(tmp_path):
    manifest = _base_c1_manifest(tmp_path)
    manifest["stage"] = "S4"
    manifest["route_profile"] = "personal-local-readonly"
    manifest["dependencies"] = [{"stage": "S3"}]
    errors = validate("S4", manifest, tmp_path)
    assert any("依赖不符" in error for error in errors)
    assert any("未知依赖阶段" in error for error in errors)


def test_platform_reference_checks_cannot_replace_personal_s4(tmp_path):
    manifest = _base_c1_manifest(tmp_path)
    manifest["stage"] = "S4"
    manifest["route_profile"] = "personal-local-readonly"
    manifest["dependencies"] = []
    manifest["checks"] = [
        {
            "id": "durable-run-state",
            "status": "passed",
            "artifacts": manifest["checks"][0]["artifacts"],
        }
    ]
    errors = validate("S4", manifest, tmp_path)
    assert any("tool-governance" in error for error in errors)
    assert any("chat-runtime-regression" in error for error in errors)


def test_evidence_commit_requires_clean_committed_manifest(tmp_path, monkeypatch):
    manifest_path = REPO_ROOT / "docs/roadmap/current-release/evidence/C1/manifest.json"

    class _Result:
        def __init__(self, stdout="", returncode=0):
            self.stdout = stdout
            self.returncode = returncode

    monkeypatch.setattr(
        "validate_stage_evidence._git",
        lambda args: _Result("?? manifest.json\n") if args[0] == "status" else _Result(),
    )
    errors = validate_evidence_commit(
        manifest_path,
        {"validated_head": _git(["rev-parse", "HEAD"])},
    )
    assert errors == ["manifest 必须先提交，且不能有未提交修改"]
