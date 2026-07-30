#!/usr/bin/env python3
"""Fail a release freeze when tracked files contain secrets or host path leaks."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

SECRET_PATTERNS = (
    ("api-key", re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b")),
    ("private-key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
)
RELEASE_PATH_PATTERNS = (
    ("host-path", re.compile(r"/(?:Users|home)/[^/\s\"']+/")),
    ("mac-temp-path", re.compile(r"/(?:private/)?var/folders/")),
    (
        "connection-string",
        re.compile(r"(?i)\b(?:postgresql(?:\+\w+)?|redis)://[^\s\"']+"),
    ),
)
PLACEHOLDERS = {
    "sk-your-deepseek-api-key",
    "sk-<redacted>",
}
RELEASE_ARTIFACT_PREFIXES = (
    "codeaware-py/openapi/",
    "docs/roadmap/current-release/evidence/",
)


def scan_text(path: str, text: str) -> list[str]:
    violations: list[str] = []
    for label, pattern in SECRET_PATTERNS:
        for match in pattern.finditer(text):
            if match.group(0) not in PLACEHOLDERS:
                violations.append(f"{path}: {label}")
                break
    if path.startswith(RELEASE_ARTIFACT_PREFIXES):
        for label, pattern in RELEASE_PATH_PATTERNS:
            if pattern.search(text):
                violations.append(f"{path}: {label}")
    return violations


def tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", "-z"],
        check=True,
        capture_output=True,
    )
    return [
        item.decode("utf-8")
        for item in result.stdout.split(b"\0")
        if item
    ]


def main() -> int:
    files = tracked_files()
    violations: list[str] = []
    if "codeaware-py/.env" in files or ".env" in files:
        violations.append("tracked .env file")

    scanned = 0
    for relative in files:
        path = REPO_ROOT / relative
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        scanned += 1
        violations.extend(scan_text(relative, text))

    if violations:
        for violation in sorted(set(violations)):
            print(f"[release-hygiene] FAIL {violation}")
        return 1
    print(
        f"[release-hygiene] PASS tracked_files={len(files)} "
        f"text_files={scanned} secrets=0 host_path_leaks=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
