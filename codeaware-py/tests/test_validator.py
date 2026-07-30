"""C1-D evidence validator route, dependency, and artifact tests."""

import hashlib
import subprocess

from validate_stage_evidence import DAG, REQUIRED_CHECKS, validate

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
    report.write_text("# C1 report\n", encoding="utf-8")
    command_log.write_text("passed\n", encoding="utf-8")
    check_artifact.write_text("passed\n", encoding="utf-8")
    return {
        "schema_version": 1,
        "stage": "C1",
        "route_profile": "current-release",
        "baseline_commit": _git(["rev-parse", "HEAD~3"]),
        "implementation_commit": head,
        "implementation_parent": _git(["rev-parse", "HEAD^"]),
        "validated_head": head,
        "dependencies": [],
        "report": {"path": "report.md", "sha256": _hash(report)},
        "commands": [
            {
                "id": "backend-unit",
                "argv": ["python", "scripts/run_tests_safe.py", "-q"],
                "cwd": "codeaware-py",
                "exit_code": 0,
                "started_at": "2026-07-30T00:00:00Z",
                "finished_at": "2026-07-30T00:01:00Z",
                "stdout": "backend.log",
                "sha256": _hash(command_log),
                "required": True,
            }
        ],
        "checks": [
            {
                "id": check_id,
                "status": "passed",
                "artifacts": [{"path": "check.log", "sha256": _hash(check_artifact)}],
            }
            for check_id in REQUIRED_CHECKS["C1"]
        ],
        "rollback": {"result": "passed"},
        "result": "passed",
    }


def test_accepts_well_formed_c1(tmp_path):
    assert validate("C1", _base_c1_manifest(tmp_path), tmp_path) == []


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
    assert DAG["S4"] == ["S2"]
    assert "S3" not in DAG
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
