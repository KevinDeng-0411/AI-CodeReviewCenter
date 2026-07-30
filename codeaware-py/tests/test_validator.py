"""C1-SAFE-HARNESS: 证据校验器逻辑测试。

用真实 Git commit + 临时 manifest 验证 validate() 的拒绝/接受判定。
不写真实 evidence 目录；只测判定逻辑。
"""

import subprocess
from pathlib import Path

import pytest

from validate_stage_evidence import DAG, REQUIRED_CHECKS, STAGE_PROFILE, validate

REPO_ROOT = Path(__file__).resolve().parents[2]


def _git(args: list[str]) -> str:
    return subprocess.run(["git", "-C", str(REPO_ROOT), *args], capture_output=True, text=True).stdout.strip()


def _base_c1_manifest(report_sha: str) -> dict:
    """良构 C1 manifest（dependencies=[]，真实 git commit，report hash 待填）。"""
    head = _git(["rev-parse", "HEAD"])
    return {
        "schema_version": 1,
        "stage": "C1",
        "route_profile": "current-release",
        "baseline_commit": _git(["rev-parse", "HEAD~3"]),
        "implementation_commit": head,
        "implementation_parent": _git(["rev-parse", "HEAD^"]),
        "validated_head": head,
        "dependencies": [],
        "report": {"path": "report.md", "sha256": report_sha},
        "commands": [{"id": "backend-unit", "exit_code": 0, "required": True, "stdout": None}],
        "checks": [{"id": c, "status": "passed", "artifacts": []} for c in REQUIRED_CHECKS["C1"]],
        "rollback": {"result": "passed"},
        "result": "passed",
    }


def test_accepts_well_formed_c1(tmp_path):
    report = tmp_path / "report.md"
    report.write_text("# C1 report\n", encoding="utf-8")
    import hashlib

    manifest = _base_c1_manifest(hashlib.sha256(report.read_bytes()).hexdigest())
    errors = validate("C1", manifest, tmp_path)
    assert errors == [], f"应通过，但有错误: {errors}"


def test_rejects_wrong_route_profile(tmp_path):
    manifest = _base_c1_manifest("x")
    manifest["route_profile"] = "personal-local-readonly"  # C1 应为 current-release
    errors = validate("C1", manifest, tmp_path)
    assert any("route_profile" in e for e in errors)


def test_rejects_missing_required_check(tmp_path):
    manifest = _base_c1_manifest("x")
    manifest["checks"] = [c for c in manifest["checks"] if c["id"] != "C1-A"]  # 删一个必需 check
    errors = validate("C1", manifest, tmp_path)
    assert any("C1-A" in e for e in errors)


def test_rejects_wrong_dependencies(tmp_path):
    # C2 应依赖 [C1]，这里故意写成 [S1]
    manifest = _base_c1_manifest("x")
    manifest["stage"] = "C2"
    manifest["route_profile"] = "current-release"
    manifest["dependencies"] = [{"stage": "S1"}]
    errors = validate("C2", manifest, tmp_path)
    assert any("依赖不符" in e for e in errors)


def test_rejects_result_not_passed(tmp_path):
    manifest = _base_c1_manifest("x")
    manifest["result"] = "failed"
    errors = validate("C1", manifest, tmp_path)
    assert any("result" in e for e in errors)


def test_rejects_bad_git_ancestry(tmp_path):
    manifest = _base_c1_manifest("x")
    # implementation_parent 故意写错（不是直接父）
    manifest["implementation_parent"] = _git(["rev-parse", "HEAD~2"])
    errors = validate("C1", manifest, tmp_path)
    assert any("implementation_parent" in e for e in errors)


def test_rejects_unknown_stage_via_main():
    import sys

    import validate_stage_evidence as v

    rc = v.main.__wrapped__ if hasattr(v.main, "__wrapped__") else None
    # 直接调 main：未知 stage 应返回 2
    sys.argv = ["validate_stage_evidence.py", "S3"]  # S3 不在合法集合
    code = v.main()
    assert code == 2


def test_s4_depends_on_s2_not_s3():
    """S4 直接依赖 S2，S3 缺失合法（不按 S(n-1) 推导）。"""
    assert DAG["S4"] == ["S2"]
    assert "S3" not in DAG
