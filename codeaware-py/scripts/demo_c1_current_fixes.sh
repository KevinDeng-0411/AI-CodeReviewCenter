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

echo "[C1 DEMO] fresh bootstrap and safe harness"
"$app_root/scripts/verify_fresh_bootstrap.sh"

echo "[C1 DEMO] route-level C1-A/C1-B/C1-C/C1-E closure"
(
  cd "$app_root"
  uv run python scripts/run_tests_safe.py \
    tests/test_chat.py::test_c1a_demo_typed_sse_degradation_abort_and_concurrency \
    tests/test_chat_summary.py::test_c1b_demo_threshold_idempotency_and_prompt_use \
    tests/test_chat_summary.py::test_c1b_demo_stream_summary_cache_failure_warns_and_completes \
    tests/test_knowledge_upload.py::test_c1c_demo_multipart_success_and_stable_failure \
    tests/test_ai_readme_snapshot.py::test_c1e_demo_route_snapshot_versions_latest_and_rejections \
    -q -s
)

after_status="$(git -C "$repo_root" status --porcelain=v1 --untracked-files=all)"
after_fingerprint="$(development_fingerprint)"
if [[ "$before_status" != "$after_status" ]]; then
  echo "[C1 DEMO] repository status changed during demo" >&2
  exit 1
fi
if [[ "$before_fingerprint" != "$after_fingerprint" ]]; then
  echo "[C1 DEMO] development Docker resource fingerprint changed" >&2
  exit 1
fi

echo "[C1 DEMO] PASS repository_status_unchanged=true development_resources_unchanged=true"
