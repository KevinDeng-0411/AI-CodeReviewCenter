#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)"
app_root="$repo_root/codeaware-py"

development_fingerprint() {
  {
    docker compose -f "$repo_root/docker-compose.yml" ps -a \
      --format '{{.ID}}|{{.Name}}|{{.State}}|{{.Image}}' 2>/dev/null | sort || true
    docker volume inspect \
      ai-center_pgdata ai-center_redisdata ai-center_ollamadata \
      --format '{{.Name}}|{{.Driver}}|{{index .Labels "com.docker.compose.project"}}' \
      2>/dev/null | sort || true
  }
}

before_status="$(git -C "$repo_root" status --porcelain=v1 --untracked-files=all)"
before_fingerprint="$(development_fingerprint)"
if [[ -n "$before_status" ]]; then
  echo "[C3 HANDOFF] worktree must be clean" >&2
  exit 1
fi

cleanup() {
  local rc=$?
  trap - EXIT INT TERM
  local after_status
  local after_fingerprint
  after_status="$(git -C "$repo_root" status --porcelain=v1 --untracked-files=all)"
  after_fingerprint="$(development_fingerprint)"
  if [[ "$before_status" != "$after_status" ]]; then
    echo "[C3 HANDOFF] repository status changed" >&2
    rc=1
  fi
  if [[ "$before_fingerprint" != "$after_fingerprint" ]]; then
    echo "[C3 HANDOFF] development Docker resource fingerprint changed" >&2
    rc=1
  fi
  if [[ $rc -eq 0 ]]; then
    echo "[C3 HANDOFF] PASS repository_status_unchanged=true development_resources_unchanged=true"
  fi
  exit "$rc"
}
trap cleanup EXIT
trap 'exit 130' INT TERM

version="$(
  cd "$app_root"
  uv run python -c 'from app.core.version import APP_VERSION; print(APP_VERSION)'
)"
echo "[C3 HANDOFF] release=$version commit=$(git -C "$repo_root" rev-parse HEAD)"

(
  cd "$app_root"
  uv run python scripts/validate_stage_evidence.py C1
  uv run python scripts/validate_stage_evidence.py C2
  uv run python scripts/export_openapi.py --check
  uv run python scripts/check_release_hygiene.py
  uv run python scripts/run_tests_safe.py \
    tests/contracts/test_release_contract.py \
    tests/evaluation/test_c3_release_metrics.py \
    -q -s
)
"$app_root/scripts/demo_c2_mocked.sh"

echo "[C3 HANDOFF] PASS fresh command=./codeaware-py/scripts/verify_current_release.sh"
echo "[C3 HANDOFF] PASS rollback command=./codeaware-py/scripts/verify_c3_rollback.sh"
echo "[C3 HANDOFF] PASS C2 committed live-smoke evidence hash revalidated"
echo "[C3 HANDOFF] LIMIT local-first single-worker no-auth no-agent current-lexical=pg_trgm"
