#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)"
app_root="$repo_root/codeaware-py"
frontend_root="$app_root/frontend"
tmp_dir="$(mktemp -d)"
before_status="$(git -C "$repo_root" status --porcelain=v1 --untracked-files=all)"

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

development_fingerprint >"$tmp_dir/development-before.txt"
started_at="$(date +%s)"

cleanup() {
  local rc=$?
  trap - EXIT INT TERM
  set +e
  development_fingerprint >"$tmp_dir/development-after.txt"
  if ! cmp -s "$tmp_dir/development-before.txt" "$tmp_dir/development-after.txt"; then
    echo "[C3 VERIFY] development Docker resource fingerprint changed" >&2
    rc=1
  fi
  local after_status
  after_status="$(git -C "$repo_root" status --porcelain=v1 --untracked-files=all)"
  if [[ "$before_status" != "$after_status" ]]; then
    echo "[C3 VERIFY] repository status changed" >&2
    rc=1
  fi
  if ! rm -r -- "$tmp_dir"; then
    echo "[C3 VERIFY] temporary directory cleanup failed" >&2
    rc=1
  fi
  if [[ $rc -eq 0 ]]; then
    echo "[C3 VERIFY] exact cleanup confirmed repository_status_unchanged=true development_resources_unchanged=true"
  fi
  exit "$rc"
}
trap cleanup EXIT
trap 'exit 130' INT TERM

run_step() {
  local label=$1
  shift
  local step_started
  local step_finished
  step_started="$(date +%s)"
  echo "[C3 VERIFY] START $label"
  "$@"
  step_finished="$(date +%s)"
  echo "[C3 VERIFY] PASS $label exit=0 seconds=$((step_finished - step_started))"
}

export NPM_CONFIG_CACHE="$tmp_dir/npm-cache"
mkdir -p "$NPM_CONFIG_CACHE"

version="$(
  cd "$app_root"
  uv run python -c 'from app.core.version import APP_VERSION; print(APP_VERSION)'
)"
frontend_version="$(
  cd "$frontend_root"
  node -p 'require("./package.json").version'
)"
commit="$(git -C "$repo_root" rev-parse HEAD)"
if [[ "$version" != "$frontend_version" ]]; then
  echo "[C3 VERIFY] backend/frontend version mismatch" >&2
  exit 1
fi
echo "[C3 VERIFY] release=$version commit=$commit"

run_step dependency-lock bash -c "cd '$app_root' && uv lock --check"
run_step compose-config docker compose -f "$repo_root/docker-compose.yml" config --quiet
run_step openapi-contract bash -c "cd '$app_root' && uv run python scripts/export_openapi.py --check"
run_step c1-evidence bash -c "cd '$app_root' && uv run python scripts/validate_stage_evidence.py C1"
run_step c2-evidence bash -c "cd '$app_root' && uv run python scripts/validate_stage_evidence.py C2"
run_step release-hygiene bash -c "cd '$app_root' && uv run python scripts/check_release_hygiene.py"
run_step fresh-bootstrap "$app_root/scripts/verify_fresh_bootstrap.sh"
run_step backend-full bash -c "cd '$app_root' && uv run python scripts/run_tests_safe.py -q"
run_step backend-coverage bash -c "cd '$app_root' && uv run python scripts/run_tests_safe.py --cov=app --cov-report=term-missing -q"
run_step api-e2e bash -c "cd '$app_root' && uv run python scripts/run_tests_safe.py tests/contracts tests/e2e -q"
run_step release-metrics bash -c "cd '$app_root' && uv run python scripts/run_tests_safe.py tests/evaluation/test_c3_release_metrics.py -q -s"
run_step c2-mocked-demo "$app_root/scripts/demo_c2_mocked.sh"
run_step frontend-install bash -c "cd '$frontend_root' && npm ci"
run_step frontend-test bash -c "cd '$frontend_root' && npm run test"
run_step frontend-lint bash -c "cd '$frontend_root' && npm run lint"
run_step frontend-build bash -c "cd '$frontend_root' && npm run build"
run_step browser-e2e bash -c "cd '$app_root' && uv run python scripts/run_tests_safe.py --browser-e2e"

finished_at="$(date +%s)"
echo "[C3 VERIFY] PASS release=$version total_seconds=$((finished_at - started_at)) browser_domains=7"
