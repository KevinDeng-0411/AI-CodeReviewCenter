#!/usr/bin/env python3
"""Validate the only machine-readable stage evidence entrypoint."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

STAGE_PROFILE = {
    "C1": "current-release",
    "C2": "current-release",
    "C3": "current-release",
    "S1": "personal-local-readonly",
    "S2": "personal-local-readonly",
    "S4": "personal-local-readonly",
    "S5": "personal-local-readonly",
}
DAG = {
    "C1": [],
    "C2": ["C1"],
    "C3": ["C2"],
    "S1": ["C3"],
    "S2": ["S1"],
    "S4": ["S2"],
    "S5": ["S4"],
}
REQUIRED_CHECKS = {
    "C1": ["C1-SAFE-HARNESS", "C1-A", "C1-B", "C1-C", "C1-D", "C1-E"],
    "C2": ["code-review", "unit-test", "ai-readme", "chat", "knowledge", "memory", "prompt"],
    "C3": ["fresh-bootstrap", "docs-contract", "rollback", "freeze-handoff"],
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
    "baseline_commit",
    "implementation_commit",
    "implementation_parent",
    "validated_head",
    "dependencies",
    "report",
    "commands",
    "checks",
    "rollback",
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
    if not path.is_file():
        errors.append(f"{label} 不存在: {rel}")
    elif sha256_file(path) != expected:
        errors.append(f"{label} sha256 不符")


def _validate_repo_cwd(cwd: Any, label: str, errors: list[str]) -> None:
    if not isinstance(cwd, str) or not cwd:
        errors.append(f"{label} cwd 缺失")
        return
    path = (REPO_ROOT / cwd).resolve()
    try:
        path.relative_to(REPO_ROOT.resolve())
    except ValueError:
        errors.append(f"{label} cwd 路径逃逸: {cwd}")


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
    if baseline and implementation and not _is_ancestor(baseline, implementation):
        errors.append(f"baseline {baseline} 不是 implementation {implementation} 的祖先")
    if parent and implementation:
        actual_parent = _git(["rev-parse", f"{implementation}^"]).stdout.strip()
        if actual_parent != parent:
            errors.append(f"implementation_parent {parent} != 实际父 {actual_parent}")
    if implementation and head and not _is_ancestor(implementation, head):
        errors.append(f"implementation {implementation} 不在 validated_head {head} 祖先链")

    report = manifest.get("report")
    if not isinstance(report, dict) or report.get("path") != "report.md":
        errors.append("report.path 必须为 report.md")
    _validate_hashed_file(manifest_dir, report, "report", errors)

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
        _validate_repo_cwd(command.get("cwd"), f"命令 {command_id}", errors)
        _validate_hashed_file(
            manifest_dir,
            {"path": command.get("stdout"), "sha256": command.get("sha256")},
            f"命令 {command_id} stdout",
            errors,
        )

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

    if (manifest.get("rollback") or {}).get("result") != "passed":
        errors.append("rollback 未通过")
    if manifest.get("result") != "passed":
        errors.append(f"result={manifest.get('result')!r} (应 'passed')")
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
