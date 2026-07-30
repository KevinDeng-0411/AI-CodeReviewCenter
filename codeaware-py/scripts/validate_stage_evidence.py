#!/usr/bin/env python3
"""validate_stage_evidence.py - 阶段证据校验器（C1-SAFE-HARNESS）。

校验 docs/roadmap/{current-release|chat-to-agent}/evidence/{stage}/manifest.json：
- JSON 结构 + route_profile + stage 一致
- 依赖 DAG（route_profile+stage -> 合法直接依赖，不按 S(n-1) 推导）
- Git 祖先（baseline 是 implementation 祖先；implementation_parent 是直接父；validated_head 含 implementation）
- 必需命令 exit_code=0 + 产物 SHA-256
- required checks 全 passed + 产物 hash
- report.md SHA-256
- rollback passed
- result == "passed"

调用：(cd codeaware-py && uv run python scripts/validate_stage_evidence.py C1)
只有 result="passed" 可作为有效阶段入口；failed/limited 不解锁下一阶段。
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]  # ai-center/

# route_profile by stage
STAGE_PROFILE = {
    "C1": "current-release", "C2": "current-release", "C3": "current-release",
    "S1": "personal-local-readonly", "S2": "personal-local-readonly",
    "S4": "personal-local-readonly", "S5": "personal-local-readonly",
}
# 显式能力 DAG（不按编号减一推导；S4 直接依赖 S2，S3 缺失合法）
DAG = {
    "C1": [], "C2": ["C1"], "C3": ["C2"],
    "S1": ["C3"], "S2": ["S1"], "S4": ["S2"], "S5": ["S4"],
}
REQUIRED_CHECKS = {
    "C1": ["C1-SAFE-HARNESS", "C1-A", "C1-B", "C1-C", "C1-D", "C1-E"],
    "C2": ["code-review", "unit-test", "ai-readme", "chat", "knowledge", "memory", "prompt"],
    "C3": ["fresh-bootstrap", "docs-contract", "rollback", "freeze-handoff"],
    "S1": ["migration-scope", "api-scope", "retrieval-isolation", "frontend-scope", "rollback"],
    "S2": ["behavior-parity", "architecture-boundary", "uow-transaction", "rollback"],
    "S4": ["tool-governance", "budget-loop", "citation-persistence", "chat-runtime-regression", "security-negative", "rollback"],
    "S5": ["repository-provenance", "scanner-security", "index-idempotency", "tool-citation", "source-unchanged", "profile-safety-locks", "rollback"],
}

REQUIRED_KEYS = [
    "schema_version", "stage", "route_profile", "baseline_commit",
    "implementation_commit", "implementation_parent", "validated_head",
    "dependencies", "report", "commands", "checks", "rollback", "result",
]


def manifest_path_for(stage: str) -> Path:
    profile = STAGE_PROFILE[stage]
    subdir = "current-release" if profile == "current-release" else "chat-to-agent"
    return REPO_ROOT / "docs" / "roadmap" / subdir / "evidence" / stage / "manifest.json"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _git(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(REPO_ROOT), *args], capture_output=True, text=True)


def _is_ancestor(a: str, b: str) -> bool:
    return _git(["merge-base", "--is-ancestor", a, b]).returncode == 0


def validate(stage: str, manifest: dict, manifest_dir: Path) -> list[str]:
    """返回错误列表；空列表表示通过。"""
    errors: list[str] = []

    # 1. 结构
    for k in REQUIRED_KEYS:
        if k not in manifest:
            errors.append(f"缺字段: {k}")

    # 2. stage / route_profile
    if manifest.get("stage") != stage:
        errors.append(f"stage 不匹配: manifest={manifest.get('stage')!r} arg={stage!r}")
    expected_profile = STAGE_PROFILE.get(stage)
    if expected_profile and manifest.get("route_profile") != expected_profile:
        errors.append(f"route_profile 应为 {expected_profile!r}, 实为 {manifest.get('route_profile')!r}")

    # 3. 依赖 DAG
    deps = manifest.get("dependencies", []) or []
    dep_stages = sorted(d.get("stage") for d in deps if isinstance(d, dict))
    legal = sorted(DAG.get(stage, []))
    if dep_stages != legal:
        errors.append(f"依赖不符: manifest={dep_stages} 合法={legal}")
    for d in deps:
        if not isinstance(d, dict):
            continue
        dep_stage = d.get("stage")
        if dep_stage not in DAG:
            continue
        dep_mp = manifest_path_for(dep_stage)
        if not dep_mp.exists():
            errors.append(f"依赖 {dep_stage} manifest 不存在: {dep_mp}")
            continue
        if d.get("manifest_sha256") and sha256_file(dep_mp) != d["manifest_sha256"]:
            errors.append(f"依赖 {dep_stage} manifest sha256 不符")
        try:
            dep_manifest = json.loads(dep_mp.read_text())
        except Exception:
            errors.append(f"依赖 {dep_stage} manifest JSON 解析失败")
            continue
        if dep_manifest.get("result") != "passed":
            errors.append(f"依赖 {dep_stage} result={dep_manifest.get('result')} (应 passed)")
        if d.get("validated_commit") and dep_manifest.get("validated_head") != d["validated_commit"]:
            errors.append(f"依赖 {dep_stage} validated_commit 与 manifest 不一致")

    # 4. Git 祖先
    impl = manifest.get("implementation_commit")
    base = manifest.get("baseline_commit")
    parent = manifest.get("implementation_parent")
    head = manifest.get("validated_head")
    if base and impl and not _is_ancestor(base, impl):
        errors.append(f"baseline {base} 不是 implementation {impl} 的祖先")
    if parent and impl:
        actual_parent = _git(["rev-parse", f"{impl}^"]).stdout.strip()
        if actual_parent != parent:
            errors.append(f"implementation_parent {parent} != 实际父 {actual_parent}")
    if impl and head and not _is_ancestor(impl, head):
        errors.append(f"implementation {impl} 不在 validated_head {head} 祖先链")

    # 5. report hash
    report = manifest.get("report") or {}
    if report.get("path"):
        rp = (manifest_dir / report["path"]).resolve()
        try:
            rp.relative_to(manifest_dir.resolve())  # 路径不逃逸
        except ValueError:
            errors.append(f"report 路径逃逸: {report['path']}")
        else:
            if not rp.exists():
                errors.append(f"report 不存在: {rp}")
            elif report.get("sha256") and sha256_file(rp) != report["sha256"]:
                errors.append("report sha256 不符")

    # 6. commands
    for cmd in manifest.get("commands", []) or []:
        cid = cmd.get("id", "?")
        if cmd.get("required") and cmd.get("exit_code") != 0:
            errors.append(f"命令 {cid} exit_code={cmd.get('exit_code')} (应 0)")
        if cmd.get("stdout"):
            ap = (manifest_dir / cmd["stdout"]).resolve()
            if ap.exists() and cmd.get("sha256") and sha256_file(ap) != cmd["sha256"]:
                errors.append(f"命令 {cid} stdout hash 不符")

    # 7. checks
    check_map = {c.get("id"): c for c in (manifest.get("checks") or []) if isinstance(c, dict)}
    for rc in REQUIRED_CHECKS.get(stage, []):
        if rc not in check_map:
            errors.append(f"缺 required check: {rc}")
        elif check_map[rc].get("status") != "passed":
            errors.append(f"check {rc} 状态={check_map[rc].get('status')} (应 passed)")

    # 8. rollback
    if (manifest.get("rollback") or {}).get("result") != "passed":
        errors.append("rollback 未通过")

    # 9. result
    if manifest.get("result") != "passed":
        errors.append(f"result={manifest.get('result')!r} (应 'passed')")

    return errors


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in STAGE_PROFILE:
        print(f"用法: validate_stage_evidence.py <{'|'.join(STAGE_PROFILE)}>", file=sys.stderr)
        print(f"未知 stage: {sys.argv[1] if len(sys.argv) > 1 else '(无)'}", file=sys.stderr)
        return 2
    stage = sys.argv[1]
    mp = manifest_path_for(stage)
    if not mp.exists():
        print(f"✗ manifest 不存在: {mp}", file=sys.stderr)
        return 1
    try:
        manifest = json.loads(mp.read_text())
    except Exception as e:
        print(f"✗ manifest JSON 解析失败: {e}", file=sys.stderr)
        return 1
    errors = validate(stage, manifest, mp.parent)
    if errors:
        print(f"✗ stage {stage} ({STAGE_PROFILE[stage]}) manifest 校验失败 ({len(errors)} 项):", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print(f"✓ stage {stage} ({STAGE_PROFILE[stage]}) manifest 校验通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
