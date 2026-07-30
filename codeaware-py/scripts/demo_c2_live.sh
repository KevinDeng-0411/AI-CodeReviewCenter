#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root/codeaware-py"

echo "[C2 LIVE] starting guarded release smoke"
uv run python scripts/run_tests_safe.py --live-eval
echo "[C2 LIVE] PASS"
